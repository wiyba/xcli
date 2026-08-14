use std::collections::BTreeSet;
use std::time::Duration;

use anyhow::{Context, Result, ensure};
use reqwest::Method;

use crate::config::Config;
use crate::links;
use crate::remote;
use crate::state;

fn human(bytes: u64) -> String {
    match [
        ("T", 1u64 << 40),
        ("G", 1 << 30),
        ("M", 1 << 20),
        ("K", 1 << 10),
    ]
    .into_iter()
    .find(|(_, size)| bytes >= *size)
    {
        Some((unit, size)) => format!("{:.1}{unit}", bytes as f64 / size as f64),
        None => bytes.to_string(),
    }
}

fn client() -> Result<reqwest::Client> {
    Ok(reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()?)
}

fn print_table(rows: &[Vec<String>]) {
    let cols = rows[0].len();
    let widths: Vec<usize> = (0..cols)
        .map(|i| rows.iter().map(|r| r[i].chars().count()).max().unwrap_or(0))
        .collect();
    for row in rows {
        let line = row
            .iter()
            .zip(&widths)
            .map(|(cell, w)| format!("{cell:<w$}"))
            .collect::<Vec<_>>()
            .join("  ");
        println!("{}", line.trim_end());
    }
}

pub async fn ls(cfg: &Config) -> Result<()> {
    let c = client()?;
    let mut usages = Vec::new();
    for h in &cfg.hosts {
        let usage = match remote::fetch_usage(&c, &cfg.token, h).await {
            Ok(u) => Some(u),
            Err(e) => {
                eprintln!("{}: {e:#}", h.name);
                None
            }
        };
        usages.push(usage);
    }
    let blocked: BTreeSet<String> = state::load(&cfg.state_dir, "blocked.json");
    let mut header = vec!["on".to_string(), "b".to_string(), "user".to_string()];
    header.extend(cfg.hosts.iter().map(|h| h.name.clone()));
    let mut rows = vec![header];
    let names = cfg
        .users
        .iter()
        .map(|u| &u.user)
        .chain(cfg.machines.iter().filter(|m| m.client).map(|m| &m.name));
    for name in names {
        let on: String = cfg
            .hosts
            .iter()
            .zip(&usages)
            .filter(|(_, usage)| {
                usage
                    .as_ref()
                    .is_some_and(|usage| usage.online.iter().any(|o| o == name))
            })
            .filter_map(|(h, _)| h.name.chars().next())
            .collect();
        let mut row = vec![
            if on.is_empty() { "-".to_string() } else { on },
            if blocked.contains(name) { "b" } else { "-" }.to_string(),
            name.clone(),
        ];
        row.extend(usages.iter().map(|usage| match usage {
            Some(usage) => human(usage.users.get(name).map(|t| t.total()).unwrap_or(0)),
            None => "?".to_string(),
        }));
        rows.push(row);
    }
    print_table(&rows);
    Ok(())
}

pub async fn status(cfg: &Config) -> Result<()> {
    let c = client()?;
    for h in &cfg.hosts {
        let up = matches!(
            remote::request(&c, &cfg.token, h, Method::GET, "/health", None).await,
            Ok(r) if r.status().is_success()
        );
        println!("{:<12} {}", h.name, if up { "up" } else { "down" });
    }
    Ok(())
}

pub async fn set_blocked(cfg: &Config, user: &str, blocked: bool) -> Result<()> {
    let u = cfg
        .user(user)
        .with_context(|| format!("no such user: {user}"))?;
    ensure!(!(blocked && u.admin), "cannot block admin: {user}");
    broadcast(cfg, if blocked { "/block" } else { "/unblock" }, Some(user)).await
}

pub async fn sync(cfg: &Config) -> Result<()> {
    broadcast(cfg, "/sync", None).await
}

async fn broadcast(cfg: &Config, path: &str, body: Option<&str>) -> Result<()> {
    let c = client()?;
    let mut failed = Vec::new();
    for h in &cfg.hosts {
        let body = body.map(str::to_string);
        match remote::request(&c, &cfg.token, h, Method::POST, path, body).await {
            Ok(r) if r.status().is_success() => println!("{}: ok", h.name),
            Ok(r) => {
                println!(
                    "{}: {} {}",
                    h.name,
                    r.status(),
                    r.text().await.unwrap_or_default()
                );
                failed.push(h.name.clone());
            }
            Err(e) => {
                println!("{}: {e:#}", h.name);
                failed.push(h.name.clone());
            }
        }
    }
    ensure!(failed.is_empty(), "not applied on: {}", failed.join(", "));
    Ok(())
}

pub async fn export(cfg: &Config, user: &str) -> Result<()> {
    let mut cfg = cfg.clone();
    remote::resolve_addrs(&client()?, &mut cfg, Some(3)).await?;
    let u = cfg
        .user(user)
        .with_context(|| format!("no such user: {user}"))?;
    let blocked = state::load::<BTreeSet<String>>(&cfg.state_dir, "blocked.json").contains(user);
    let sid = u.uuid.get(..8).context("bad uuid")?;
    let mark = if blocked { " [BLOCKED]" } else { "" };
    println!("https://{}/{sid}{mark}\n", cfg.sub_domain);
    let links = if blocked {
        links::blocked_links()
    } else {
        links::user_links(u, &cfg.hosts)
    };
    for link in links {
        println!("{}", link.uri);
    }
    Ok(())
}
