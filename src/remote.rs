use std::time::Duration;

use anyhow::{Context, Result};
use reqwest::{Client, Method, Response};

use crate::config::{Config, Host};
use crate::state::Usage;

const DOH: &[&str] = &["https://1.1.1.1/dns-query", "https://8.8.8.8/resolve"];

pub async fn resolve_addrs(
    client: &Client,
    cfg: &mut Config,
    max_attempts: Option<u32>,
) -> Result<()> {
    for h in &mut cfg.hosts {
        if h.addr.is_some() {
            continue;
        }
        let mut attempt = 0u32;
        h.addr = loop {
            attempt += 1;
            match doh_resolve(client, &h.fqdn).await {
                Ok(ip) => break Some(ip),
                Err(e) => {
                    eprintln!("resolve {}: {e:#}", h.fqdn);
                    if max_attempts.is_some_and(|m| attempt >= m) {
                        anyhow::bail!("resolve {} failed after {attempt} attempts", h.fqdn);
                    }
                    tokio::time::sleep(Duration::from_secs(5)).await;
                }
            }
        };
    }
    Ok(())
}

pub async fn doh_resolve(client: &Client, name: &str) -> Result<String> {
    let mut last = None;
    for base in DOH {
        let res = async {
            let r = client
                .get(format!("{base}?name={name}&type=A"))
                .header("accept", "application/dns-json")
                .send()
                .await?
                .error_for_status()?;
            let v: serde_json::Value = r.json().await?;
            v["Answer"]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|a| a["type"].as_i64() == Some(1))
                .filter_map(|a| a["data"].as_str())
                .next()
                .map(str::to_string)
                .context("no A records")
        }
        .await;
        match res {
            Ok(ip) => return Ok(ip),
            Err(e) => last = Some(e),
        }
    }
    Err(last.unwrap())
}

pub async fn request(
    client: &Client,
    token: &str,
    host: &Host,
    method: Method,
    path: &str,
    body: Option<String>,
) -> Result<Response> {
    let urls = match &host.api {
        Some(base) => vec![format!("{base}{path}")],
        None => vec![
            format!("https://{}:8443{path}", host.fqdn),
            format!("https://{}:443{path}", host.fqdn),
        ],
    };
    let mut last = None;
    for url in &urls {
        let mut req = client.request(method.clone(), url).bearer_auth(token);
        if let Some(b) = &body {
            req = req.body(b.clone());
        }
        match req.send().await {
            Ok(r) => return Ok(r),
            Err(e) => last = Some(e),
        }
    }
    Err(last.unwrap().into())
}

pub async fn fetch_usage(client: &Client, token: &str, host: &Host) -> Result<Usage> {
    let r = request(client, token, host, Method::GET, "/traffic", None).await?;
    Ok(r.error_for_status()?.json().await?)
}
