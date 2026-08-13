use std::collections::BTreeMap;
use std::path::PathBuf;

use anyhow::{Context, Result};
use serde::Deserialize;

#[derive(Clone, Deserialize)]
pub struct Config {
    pub support_url: String,
    pub sub_domain: String,
    pub token: String,
    #[serde(default)]
    pub node: Option<String>,
    #[serde(default = "default_state_dir")]
    pub state_dir: PathBuf,
    #[serde(default = "default_serve_listen")]
    pub serve_listen: String,
    #[serde(default = "default_agent_listen")]
    pub agent_listen: String,
    #[serde(default = "default_xray_api")]
    pub xray_api: String,
    pub hosts: Vec<Host>,
    pub users: Vec<User>,
}

#[derive(Clone, Deserialize)]
pub struct Host {
    pub name: String,
    pub flag: String,
    pub fqdn: String,
    #[serde(default)]
    pub addr: Option<String>,
    #[serde(default)]
    pub api: Option<String>,
    pub link: Link,
}

#[derive(Clone, Deserialize)]
pub struct Link {
    pub scheme: String,
    pub port: u16,
    #[serde(default)]
    pub tag: String,
    #[serde(default)]
    pub params: BTreeMap<String, String>,
}

#[derive(Clone, Deserialize)]
pub struct User {
    pub user: String,
    pub uuid: String,
    pub admin: bool,
}

fn default_state_dir() -> PathBuf {
    "/var/lib/xcli".into()
}

fn default_serve_listen() -> String {
    "127.0.0.1:9999".into()
}

fn default_agent_listen() -> String {
    "127.0.0.1:10086".into()
}

fn default_xray_api() -> String {
    "127.0.0.1:10085".into()
}

impl Config {
    pub fn user(&self, name: &str) -> Option<&User> {
        self.users.iter().find(|u| u.user == name)
    }

    pub fn user_by_sid(&self, sid: &str) -> Option<&User> {
        self.users.iter().find(|u| u.uuid.get(..8) == Some(sid))
    }

    pub fn local(&self) -> Result<&Host> {
        let node = self.node.as_deref().context("config has no node")?;
        self.hosts
            .iter()
            .find(|h| h.name == node)
            .with_context(|| format!("no host entry for node {node}"))
    }
}

pub fn load(path: &str) -> Result<Config> {
    let data = std::fs::read(path).with_context(|| format!("read config {path}"))?;
    serde_json::from_slice(&data).with_context(|| format!("parse config {path}"))
}
