use std::collections::{BTreeSet, HashMap};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use anyhow::Result;
use axum::Router;
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode, header};
use axum::response::{Html, IntoResponse, Response};
use axum::routing::get;
use base64::prelude::*;
use fast_qr::convert::Builder;
use fast_qr::convert::svg::SvgBuilder;
use fast_qr::{ECL, QRBuilder};
use tokio::sync::RwLock;
use tokio::time::Instant;

use crate::config::{Config, Host};
use crate::links::{blocked_links, user_links};
use crate::remote;
use crate::state::{self, Usage};

const USAGE_TTL: Duration = Duration::from_secs(60);
const RESOLVE_RETRY: Duration = Duration::from_secs(5);
const RESOLVE_REFRESH: Duration = Duration::from_secs(300);

const BROWSERS: &[&str] = &[
    "Mozilla",
    "Chrome",
    "Safari",
    "Firefox",
    "Opera",
    "Edge",
    "TelegramBot",
    "WhatsApp",
];

struct App {
    cfg: Config,
    hosts: RwLock<Vec<Host>>,
    env: minijinja::Environment<'static>,
    client: reqwest::Client,
    cache: RwLock<HashMap<String, Usage>>,
    fetched: RwLock<Option<Instant>>,
    refreshing: AtomicBool,
}

pub async fn run(cfg: Config) -> Result<()> {
    let mut env = minijinja::Environment::new();
    env.add_template("index.html", include_str!("../templates/index.html"))?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()?;
    let app = Arc::new(App {
        hosts: RwLock::new(cfg.hosts.clone()),
        cfg,
        env,
        client,
        cache: RwLock::new(HashMap::new()),
        fetched: RwLock::new(None),
        refreshing: AtomicBool::new(false),
    });
    tokio::spawn(resolve_task(app.clone()));
    let router = Router::new()
        .route("/", get(teapot))
        .route("/static/{file}", get(static_file))
        .route("/{sid}", get(subscription))
        .with_state(app.clone());
    let listener = tokio::net::TcpListener::bind(&app.cfg.serve_listen).await?;
    axum::serve(listener, router).await?;
    Ok(())
}

async fn teapot() -> StatusCode {
    StatusCode::IM_A_TEAPOT
}

async fn static_file(Path(file): Path<String>) -> Response {
    let (body, mime): (&'static [u8], &str) = match file.as_str() {
        "favicon.ico" => (include_bytes!("../static/favicon.ico"), "image/x-icon"),
        "apple-touch-icon.png" => (
            include_bytes!("../static/apple-touch-icon.png"),
            "image/png",
        ),
        "icon-192.png" => (include_bytes!("../static/icon-192.png"), "image/png"),
        "icon-512.png" => (include_bytes!("../static/icon-512.png"), "image/png"),
        _ => return StatusCode::NOT_FOUND.into_response(),
    };
    ([(header::CONTENT_TYPE, mime)], body).into_response()
}

async fn subscription(
    State(app): State<Arc<App>>,
    Path(sid): Path<String>,
    headers: HeaderMap,
) -> Response {
    let Some(user) = app.cfg.user_by_sid(&sid) else {
        return StatusCode::IM_A_TEAPOT.into_response();
    };
    maybe_refresh(&app).await;
    let blocked =
        state::load::<BTreeSet<String>>(&app.cfg.state_dir, "blocked.json").contains(&user.user);
    let hosts = app.hosts.read().await.clone();
    let links = if blocked {
        blocked_links(hosts.len())
    } else {
        user_links(user, &hosts)
    };
    let sub_url = format!("https://{}/{sid}", app.cfg.sub_domain);

    let hdr = |name| {
        headers
            .get(name)
            .and_then(|v: &axum::http::HeaderValue| v.to_str().ok())
            .unwrap_or("")
    };
    let is_browser = hdr(header::ACCEPT).contains("text/html")
        || BROWSERS.iter().any(|b| hdr(header::USER_AGENT).contains(b));
    if is_browser {
        let qr = QRBuilder::new(sub_url.as_str())
            .ecl(ECL::M)
            .build()
            .map(|code| {
                SvgBuilder::default()
                    .module_color("#a3a3a3")
                    .background_color("#121212")
                    .to_str(&code)
            })
            .unwrap_or_default();
        let page = app
            .env
            .get_template("index.html")
            .unwrap()
            .render(minijinja::context! {
                username => user.user,
                sub_url => sub_url,
                links => links,
                blocked => blocked,
                qr => qr,
            });
        return match page {
            Ok(html) => Html(html).into_response(),
            Err(e) => {
                eprintln!("render {sid}: {e:#}");
                StatusCode::INTERNAL_SERVER_ERROR.into_response()
            }
        };
    }

    let (up, down) = {
        let cache = app.cache.read().await;
        app.cfg
            .hosts
            .iter()
            .filter_map(|h| cache.get(&h.name))
            .filter_map(|u| u.users.get(&user.user))
            .fold((0u64, 0u64), |(up, down), t| (up + t.up, down + t.down))
    };
    let body = links
        .iter()
        .map(|l| l.uri.as_str())
        .collect::<Vec<_>>()
        .join("\n");
    let warn = if blocked { "⚠️ " } else { "" };
    let title = format!("{warn}веба впн for {}", user.user);
    (
        [
            (
                "profile-title",
                format!("base64:{}", BASE64_STANDARD.encode(title)),
            ),
            (
                "subscription-userinfo",
                format!("upload={up}; download={down}; total=0; expire=2276640000"),
            ),
            ("support-url", app.cfg.support_url.clone()),
        ],
        BASE64_STANDARD.encode(body),
    )
        .into_response()
}

async fn resolve_task(app: Arc<App>) {
    let dynamic: Vec<(usize, String)> = app
        .cfg
        .hosts
        .iter()
        .enumerate()
        .filter(|(_, h)| h.addr.is_none())
        .map(|(i, h)| (i, h.fqdn.clone()))
        .collect();
    if dynamic.is_empty() {
        return;
    }
    loop {
        for (i, fqdn) in &dynamic {
            match remote::doh_resolve(&app.client, fqdn).await {
                Ok(ip) => {
                    let mut hosts = app.hosts.write().await;
                    if hosts[*i].addr.as_deref() != Some(ip.as_str()) {
                        eprintln!("resolved {fqdn} -> {ip}");
                        hosts[*i].addr = Some(ip);
                    }
                }
                Err(e) => eprintln!("resolve {fqdn}: {e:#}"),
            }
        }
        let unresolved = app.hosts.read().await.iter().any(|h| h.addr.is_none());
        tokio::time::sleep(if unresolved {
            RESOLVE_RETRY
        } else {
            RESOLVE_REFRESH
        })
        .await;
    }
}

async fn maybe_refresh(app: &Arc<App>) {
    let fresh = app
        .fetched
        .read()
        .await
        .is_some_and(|t| t.elapsed() < USAGE_TTL);
    if fresh || app.refreshing.swap(true, Ordering::SeqCst) {
        return;
    }
    let app = app.clone();
    tokio::spawn(async move {
        for h in &app.cfg.hosts {
            match remote::fetch_usage(&app.client, &app.cfg.token, h).await {
                Ok(u) => {
                    app.cache.write().await.insert(h.name.clone(), u);
                }
                Err(e) => eprintln!("traffic {}: {e:#}", h.name),
            }
        }
        *app.fetched.write().await = Some(Instant::now());
        app.refreshing.store(false, Ordering::SeqCst);
    });
}
