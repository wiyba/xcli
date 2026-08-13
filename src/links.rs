use serde::Serialize;

use crate::config::{Host, User};

#[derive(Serialize)]
pub struct Entry {
    pub uri: String,
    pub label: String,
    pub flag: String,
    pub name: String,
    pub host: String,
}

fn entry(uri: String, flag: &str, name: &str, host: &str) -> Entry {
    Entry {
        uri: format!("{uri}#{}", urlencoding::encode(&format!("{flag} {name}"))),
        label: format!("{flag} {name}"),
        flag: flag.into(),
        name: name.into(),
        host: host.into(),
    }
}

pub fn user_links(user: &User, hosts: &[Host]) -> Vec<Entry> {
    hosts
        .iter()
        .map(|h| {
            let query: Vec<String> = h
                .link
                .params
                .iter()
                .map(|(k, v)| format!("{k}={}", urlencoding::encode(v)))
                .collect();
            let uri = format!(
                "{}://{}@{}:{}?{}",
                h.link.scheme,
                user.uuid,
                h.addr.as_deref().unwrap_or(&h.fqdn),
                h.link.port,
                query.join("&")
            );
            entry(uri, &h.flag, &h.name, &h.name)
        })
        .collect()
}

pub fn blocked_links() -> Vec<Entry> {
    vec![entry(
        "vless://00000000-0000-0000-0000-000000000000@0.0.0.0:443?security=none".into(),
        "⚠️",
        "blocked, t.me/wiybaa to renew",
        "",
    )]
}
