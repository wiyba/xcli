use std::collections::BTreeSet;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::Result;
use axum::extract::{Request, State};
use axum::http::{StatusCode, header};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use tokio::sync::{Mutex, RwLock};
use tokio::time::Instant;

use crate::config::Config;
use crate::state::{self, Usage};
use crate::xray::Xray;

const TICK: Duration = Duration::from_secs(60);
const DEBOUNCE: Duration = Duration::from_secs(3);
const ONLINE_TTL: u64 = 180;

struct Agent {
    cfg: Config,
    tag: String,
    flow: String,
    xray: Xray,
    blocked: RwLock<BTreeSet<String>>,
    usage: RwLock<Usage>,
    gate: Mutex<Option<Instant>>,
}

pub async fn run(cfg: Config) -> Result<()> {
    let local = cfg.local()?;
    let agent = Arc::new(Agent {
        tag: local.link.tag.clone(),
        flow: local.link.params.get("flow").cloned().unwrap_or_default(),
        xray: Xray::new(&cfg.xray_api)?,
        blocked: RwLock::new(state::load(&cfg.state_dir, "blocked.json")),
        usage: RwLock::new(state::load(&cfg.state_dir, "usage.json")),
        gate: Mutex::new(None),
        cfg,
    });
    tokio::spawn(tick_loop(agent.clone()));

    let protected = Router::new()
        .route("/traffic", get(traffic))
        .route("/block", post(block))
        .route("/unblock", post(unblock))
        .route("/sync", post(sync_handler))
        .route_layer(middleware::from_fn_with_state(agent.clone(), auth));
    let router = Router::new()
        .route("/health", get(health))
        .merge(protected)
        .with_state(agent.clone());
    let listener = tokio::net::TcpListener::bind(&agent.cfg.agent_listen).await?;
    axum::serve(listener, router).await?;
    Ok(())
}

async fn auth(State(agent): State<Arc<Agent>>, req: Request, next: Next) -> Response {
    let want = format!("Bearer {}", agent.cfg.token);
    let got = req
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok());
    if got == Some(want.as_str()) {
        next.run(req).await
    } else {
        StatusCode::UNAUTHORIZED.into_response()
    }
}

async fn health(State(agent): State<Arc<Agent>>) -> StatusCode {
    if agent.xray.alive().await {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    }
}

async fn traffic(State(agent): State<Arc<Agent>>) -> Json<Usage> {
    collect_gated(&agent).await;
    Json(agent.usage.read().await.clone())
}

async fn block(State(agent): State<Arc<Agent>>, body: String) -> Response {
    set_blocked(&agent, body.trim(), true).await
}

async fn unblock(State(agent): State<Arc<Agent>>, body: String) -> Response {
    set_blocked(&agent, body.trim(), false).await
}

async fn sync_handler(State(agent): State<Arc<Agent>>) -> Response {
    synced(&agent).await
}

async fn synced(agent: &Agent) -> Response {
    match sync(agent).await {
        Ok(()) => StatusCode::OK.into_response(),
        Err(e) => {
            eprintln!("sync: {e:#}");
            (StatusCode::BAD_GATEWAY, format!("{e:#}")).into_response()
        }
    }
}

async fn set_blocked(agent: &Agent, user: &str, blocked: bool) -> Response {
    let Some(u) = agent.cfg.user(user) else {
        return StatusCode::NOT_FOUND.into_response();
    };
    if blocked && u.admin {
        return StatusCode::FORBIDDEN.into_response();
    }
    {
        let mut set = agent.blocked.write().await;
        if blocked {
            set.insert(user.to_string());
        } else {
            set.remove(user);
        }
        if let Err(e) = state::save(&agent.cfg.state_dir, "blocked.json", &*set) {
            eprintln!("save blocked: {e:#}");
            return StatusCode::INTERNAL_SERVER_ERROR.into_response();
        }
    }
    synced(agent).await
}

async fn tick_loop(agent: Arc<Agent>) {
    let mut tick = tokio::time::interval(TICK);
    loop {
        tick.tick().await;
        if let Err(e) = sync(&agent).await {
            eprintln!("sync: {e:#}");
        }
        collect_gated(&agent).await;
    }
}

async fn collect_gated(agent: &Agent) {
    let mut last = agent.gate.lock().await;
    if last.is_none_or(|t| t.elapsed() >= DEBOUNCE) {
        match collect(agent).await {
            Ok(()) => *last = Some(Instant::now()),
            Err(e) => eprintln!("collect: {e:#}"),
        }
    }
}

async fn collect(agent: &Agent) -> Result<()> {
    let traffic = agent.xray.traffic(true).await?;
    let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let mut usage = agent.usage.write().await;
    for (email, dir, value) in traffic {
        if value == 0 {
            continue;
        }
        usage.seen.insert(email.clone(), now);
        let entry = usage.users.entry(email).or_default();
        match dir.as_str() {
            "uplink" => entry.up += value,
            "downlink" => entry.down += value,
            _ => {}
        }
    }
    usage.online = usage
        .seen
        .iter()
        .filter(|(_, seen)| now.saturating_sub(**seen) <= ONLINE_TTL)
        .map(|(email, _)| email.clone())
        .collect();
    usage.collected_at = now;
    state::save(&agent.cfg.state_dir, "usage.json", &*usage)
}

async fn sync(agent: &Agent) -> Result<()> {
    let blocked = agent.blocked.read().await.clone();
    let desired: Vec<_> = agent
        .cfg
        .users
        .iter()
        .filter(|u| !blocked.contains(&u.user))
        .collect();
    let actual = agent.xray.users(&agent.tag).await?;
    for u in desired.iter().filter(|u| !actual.contains(&u.user)) {
        agent
            .xray
            .add_user(&agent.tag, &u.user, &u.uuid, &agent.flow)
            .await?;
        println!("+ {}", u.user);
    }
    for email in actual.iter().filter(|e| {
        !desired.iter().any(|u| &u.user == *e)
            && !agent.cfg.machines.iter().any(|m| &m.name == *e)
    }) {
        agent.xray.remove_user(&agent.tag, email).await?;
        println!("- {email}");
    }
    Ok(())
}
