use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, ensure};
use axum::extract::State;
use axum::http::header::AUTHORIZATION;
use axum::http::{HeaderMap, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use tonic::transport::Endpoint;

mod pb {
    tonic::include_proto!("xray.app.stats.command");
}

use pb::QueryStatsRequest;
use pb::stats_service_client::StatsServiceClient;

const TICK: Duration = Duration::from_secs(60);
const ONLINE: u64 = 180;

#[derive(Clone, Copy, Default, Serialize, Deserialize)]
struct Traffic {
    up: u64,
    down: u64,
}

#[derive(Clone, Default, Serialize, Deserialize)]
struct Usage {
    users: BTreeMap<String, Traffic>,
    seen: BTreeMap<String, u64>,
}

struct App {
    usage: RwLock<Usage>,
    secret: Option<String>,
}

fn env(name: &str, default: &str) -> String {
    std::env::var(name).unwrap_or_else(|_| default.into())
}

fn secret() -> Result<Option<String>> {
    let Ok(path) = std::env::var("XCLI_SECRET") else {
        return Ok(None);
    };
    let token = std::fs::read_to_string(&path).with_context(|| format!("read {path}"))?;
    Ok(Some(token.trim().into()))
}

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs())
}

fn human(bytes: u64) -> String {
    [
        ("T", 1u64 << 40),
        ("G", 1 << 30),
        ("M", 1 << 20),
        ("K", 1 << 10),
    ]
    .into_iter()
    .find(|(_, size)| bytes >= *size)
    .map_or(bytes.to_string(), |(unit, size)| {
        format!("{:.1}{unit}", bytes as f64 / size as f64)
    })
}

fn save(path: &Path, usage: &Usage) -> Result<()> {
    let tmp = path.with_extension("tmp");
    std::fs::write(&tmp, serde_json::to_vec(usage)?)?;
    std::fs::rename(tmp, path)?;
    Ok(())
}

async fn collect(
    xray: &mut StatsServiceClient<tonic::transport::Channel>,
    app: &App,
    state: &Path,
) -> Result<()> {
    let request = QueryStatsRequest {
        pattern: "user>>>".into(),
        reset: true,
    };
    let stats = xray.query_stats(request).await?.into_inner().stat;
    let mut usage = app.usage.write().await;
    for stat in stats.iter().filter(|s| s.value > 0) {
        let ["user", name, "traffic", direction] = stat.name.split(">>>").collect::<Vec<_>>()[..]
        else {
            continue;
        };
        let traffic = usage.users.entry(name.into()).or_default();
        match direction {
            "uplink" => traffic.up += stat.value as u64,
            _ => traffic.down += stat.value as u64,
        }
        usage.seen.insert(name.into(), now());
    }
    save(state, &usage)
}

async fn poll(app: Arc<App>, state: PathBuf, channel: tonic::transport::Channel) {
    let mut xray = StatsServiceClient::new(channel);
    loop {
        if let Err(e) = collect(&mut xray, &app, &state).await {
            eprintln!("collect: {e:#}");
        }
        tokio::time::sleep(TICK).await;
    }
}

async fn serve(State(app): State<Arc<App>>, headers: HeaderMap) -> Result<Json<Usage>, StatusCode> {
    let token = headers
        .get(AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "));
    if app.secret.is_some() && token != app.secret.as_deref() {
        return Err(StatusCode::UNAUTHORIZED);
    }
    Ok(Json(app.usage.read().await.clone()))
}

async fn run() -> Result<()> {
    let state = PathBuf::from(env("STATE_DIRECTORY", "/var/lib/xcli")).join("usage.json");
    let usage = std::fs::read(&state)
        .ok()
        .and_then(|data| serde_json::from_slice(&data).ok())
        .unwrap_or_default();
    let app = Arc::new(App {
        usage: RwLock::new(usage),
        secret: secret()?,
    });
    let channel = Endpoint::from_shared(format!("http://{}", env("XCLI_XRAY", "127.0.0.1:10085")))?
        .timeout(Duration::from_secs(10))
        .connect_lazy();
    tokio::spawn(poll(app.clone(), state, channel));
    let listener = tokio::net::TcpListener::bind(env("XCLI_LISTEN", "127.0.0.1:10086")).await?;
    axum::serve(
        listener,
        Router::new().route("/", get(serve)).with_state(app),
    )
    .await?;
    Ok(())
}

async fn fetch(client: &reqwest::Client, host: &str, secret: Option<&str>) -> Result<Usage> {
    let request = client.get(format!("https://{host}/"));
    let request = match secret {
        Some(token) => request.bearer_auth(token),
        None => request,
    };
    Ok(request.send().await?.error_for_status()?.json().await?)
}

async fn print() -> Result<()> {
    let hosts = env("XCLI_HOSTS", "");
    let hosts: Vec<&str> = hosts.split(',').filter(|h| !h.is_empty()).collect();
    ensure!(!hosts.is_empty(), "XCLI_HOSTS is not set");
    let secret = secret()?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()?;

    let mut usages = Vec::new();
    for host in &hosts {
        let usage = fetch(&client, host, secret.as_deref()).await;
        if let Err(e) = &usage {
            eprintln!("{host}: {e:#}");
        }
        usages.push(usage.unwrap_or_default());
    }

    let names: BTreeSet<&String> = usages.iter().flat_map(|u| u.users.keys()).collect();
    let width = names.iter().map(|n| n.len()).max().unwrap_or(0).max(4);
    let header: String = hosts.iter().map(|h| format!("{h:>22}")).collect();
    println!("{:<4}{:<width$}{header}", "on", "user");
    for name in names {
        let online = usages.iter().any(|u| {
            u.seen
                .get(name)
                .is_some_and(|seen| now().saturating_sub(*seen) <= ONLINE)
        });
        let row: String = usages
            .iter()
            .map(|u| u.users.get(name).map_or(0, |t| t.up + t.down))
            .map(|total| format!("{:>22}", human(total)))
            .collect();
        println!("{:<4}{name:<width$}{row}", if online { "*" } else { "-" });
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    match std::env::args().nth(1).as_deref() {
        None => print().await,
        Some("run") => run().await,
        Some(other) => anyhow::bail!("unknown command: {other}"),
    }
}
