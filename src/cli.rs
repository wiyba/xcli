use std::collections::BTreeSet;
use std::time::Duration;

use anyhow::{Context, Result, ensure};
use reqwest::Method;

use crate::config::Config;
use crate::links;
use crate::remote;
use crate::state;

const GB: u64 = 1 << 30;

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
    for u in &cfg.users {
        let on: String = cfg
            .hosts
            .iter()
            .zip(&usages)
            .filter(|(_, usage)| {
                usage
                    .as_ref()
                    .is_some_and(|usage| usage.online.iter().any(|o| o == &u.user))
            })
            .filter_map(|(h, _)| h.name.chars().next())
            .collect();
        let mut row = vec![
            if on.is_empty() { "-".to_string() } else { on },
            if blocked.contains(&u.user) { "b" } else { "-" }.to_string(),
            u.user.clone(),
        ];
        row.extend(usages.iter().map(|usage| match usage {
            Some(usage) => {
                let total = usage.users.get(&u.user).map(|t| t.total()).unwrap_or(0);
                total.div_ceil(GB).to_string()
            }
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
    let path = if blocked { "/block" } else { "/unblock" };
    let c = client()?;
    for h in &cfg.hosts {
        match remote::request(
            &c,
            &cfg.token,
            h,
            Method::POST,
            path,
            Some(user.to_string()),
        )
        .await
        {
            Ok(r) if r.status().is_success() => println!("{}: ok", h.name),
            Ok(r) => println!("{}: {}", h.name, r.status()),
            Err(e) => println!("{}: {e:#}", h.name),
        }
    }
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
        links::blocked_links(cfg.hosts.len())
    } else {
        links::user_links(u, &cfg.hosts)
    };
    for link in links {
        println!("{}", link.uri);
    }
    Ok(())
}
