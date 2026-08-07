use std::collections::BTreeSet;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, bail};
use axum::extract::{Request, State};
use axum::http::{StatusCode, header};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use tokio::sync::RwLock;

use crate::config::Config;
use crate::state::{self, Usage};

const XRAY_API: &str = "--server=127.0.0.1:10085";
const INBOUND: &str = "vless-tcp";
const COLLECT_INTERVAL: Duration = Duration::from_secs(60);
const COLLECT_DEBOUNCE: Duration = Duration::from_secs(3);

struct Agent {
    cfg: Config,
    blocked: RwLock<BTreeSet<String>>,
    usage: RwLock<Usage>,
    last_collect: tokio::sync::Mutex<Option<tokio::time::Instant>>,
}

pub async fn run(cfg: Config) -> Result<()> {
    let agent = Arc::new(Agent {
        blocked: RwLock::new(state::load(&cfg.state_dir, "blocked.json")),
        usage: RwLock::new(state::load(&cfg.state_dir, "usage.json")),
        last_collect: tokio::sync::Mutex::new(None),
        cfg,
    });
    reapply(&agent).await;
    tokio::spawn(collect_loop(agent.clone()));
    let protected = Router::new()
        .route("/traffic", get(traffic))
        .route("/block", post(block))
        .route("/unblock", post(unblock))
        .route("/reapply", post(reapply_handler))
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

async fn health() -> StatusCode {
    let active = tokio::process::Command::new("systemctl")
        .args(["is-active", "-q", "xray"])
        .status()
        .await
        .map(|s| s.success())
        .unwrap_or(false);
    if active {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    }
}

async fn traffic(State(agent): State<Arc<Agent>>) -> Json<Usage> {
    collect_debounced(&agent).await;
    Json(agent.usage.read().await.clone())
}

async fn collect_debounced(agent: &Agent) {
    let mut last = agent.last_collect.lock().await;
    if last.is_none_or(|t| t.elapsed() >= COLLECT_DEBOUNCE) {
        match collect(agent).await {
            Ok(()) => *last = Some(tokio::time::Instant::now()),
            Err(e) => eprintln!("collect: {e:#}"),
        }
    }
}

async fn block(State(agent): State<Arc<Agent>>, body: String) -> Response {
    set_blocked(&agent, body.trim(), true).await
}

async fn unblock(State(agent): State<Arc<Agent>>, body: String) -> Response {
    set_blocked(&agent, body.trim(), false).await
}

async fn reapply_handler(State(agent): State<Arc<Agent>>) -> StatusCode {
    reapply(&agent).await;
    StatusCode::OK
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
    if let Err(e) = apply(agent, user, blocked).await {
        eprintln!("apply {user}: {e:#}");
        return StatusCode::BAD_GATEWAY.into_response();
    }
    StatusCode::OK.into_response()
}

async fn reapply(agent: &Agent) {
    let blocked = agent.blocked.read().await.clone();
    for user in &blocked {
        if let Err(e) = apply(agent, user, true).await {
            eprintln!("reapply {user}: {e:#}");
        }
    }
}

async fn apply(agent: &Agent, user: &str, blocked: bool) -> Result<()> {
    if blocked {
        xray(&["api", "rmu", XRAY_API, &format!("-tag={INBOUND}"), user]).await?;
        return Ok(());
    }
    let u = agent.cfg.user(user).context("unknown user")?;
    let payload = serde_json::json!({
        "inbounds": [{
            "tag": INBOUND,
            "port": 8443,
            "protocol": "vless",
            "settings": {
                "decryption": "none",
                "clients": [{ "email": u.user, "id": u.uuid, "flow": "xtls-rprx-vision" }],
            },
        }],
    });
    let tmp = agent.cfg.state_dir.join("adu.json");
    tokio::fs::write(&tmp, serde_json::to_vec(&payload)?).await?;
    let res = xray(&[
        "api",
        "adu",
        XRAY_API,
        tmp.to_str().context("state dir path")?,
    ])
    .await;
    let _ = tokio::fs::remove_file(&tmp).await;
    res.map(drop)
}

async fn collect_loop(agent: Arc<Agent>) {
    let start = tokio::time::Instant::now() + COLLECT_INTERVAL;
    let mut tick = tokio::time::interval_at(start, COLLECT_INTERVAL);
    loop {
        tick.tick().await;
        collect_debounced(&agent).await;
    }
}

async fn collect(agent: &Agent) -> Result<()> {
    let out = xray(&[
        "api",
        "statsquery",
        XRAY_API,
        "-pattern=traffic>>>",
        "-reset",
    ])
    .await?;
    let parsed: serde_json::Value = serde_json::from_str(&out)?;
    let mut usage = agent.usage.write().await;
    for stat in parsed["stat"].as_array().into_iter().flatten() {
        let name = stat["name"].as_str().unwrap_or_default();
        let value = match &stat["value"] {
            serde_json::Value::String(s) => s.parse().unwrap_or(0),
            v => v.as_u64().unwrap_or(0),
        };
        let parts: Vec<&str> = name.split(">>>").collect();
        let &["user", email, "traffic", dir] = parts.as_slice() else {
            continue;
        };
        let entry = usage.users.entry(email.to_string()).or_default();
        match dir {
            "uplink" => entry.up += value,
            "downlink" => entry.down += value,
            _ => {}
        }
    }
    match xray(&["api", "statsgetallonlineusers", XRAY_API]).await {
        Ok(out) => {
            let parsed: serde_json::Value = serde_json::from_str(&out).unwrap_or_default();
            usage.online = parsed["users"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|n| n.as_str())
                .filter_map(|n| {
                    let p: Vec<&str> = n.split(">>>").collect();
                    if let &["user", email, "online"] = p.as_slice() {
                        Some(email.to_string())
                    } else {
                        None
                    }
                })
                .collect();
        }
        Err(e) => eprintln!("online: {e:#}"),
    }
    usage.collected_at = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    state::save(&agent.cfg.state_dir, "usage.json", &*usage)
}

async fn xray(args: &[&str]) -> Result<String> {
    let run = tokio::process::Command::new("xray").args(args).output();
    let out = tokio::time::timeout(Duration::from_secs(10), run)
        .await
        .context("xray api timeout")??;
    if !out.status.success() {
        let err = if out.stderr.is_empty() {
            &out.stdout
        } else {
            &out.stderr
        };
        bail!(
            "xray {}: {}",
            args.get(1).unwrap_or(&""),
            String::from_utf8_lossy(err).trim()
        );
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}
