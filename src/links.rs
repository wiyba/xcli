use serde::Serialize;

use crate::config::{Host, User};

#[derive(Serialize)]
pub struct Link {
    pub uri: String,
    pub label: String,
    pub flag: String,
    pub name: String,
    pub host: String,
}

fn vless_uri(uuid: &str, addr: &str, pbk: &str, sni: &str, sid: &str, label: &str) -> String {
    let q = form_urlencoded::Serializer::new(String::new())
        .append_pair("security", "reality")
        .append_pair("encryption", "none")
        .append_pair("type", "tcp")
        .append_pair("flow", "xtls-rprx-vision")
        .append_pair("alpn", "h2")
        .append_pair("headerType", "none")
        .append_pair("pbk", pbk)
        .append_pair("sni", sni)
        .append_pair("sid", sid)
        .append_pair("fp", "firefox")
        .finish();
    format!(
        "vless://{uuid}@{addr}:8443?{q}#{}",
        urlencoding::encode(label)
    )
}

pub fn user_links(user: &User, hosts: &[Host]) -> Vec<Link> {
    hosts
        .iter()
        .map(|h| {
            let label = format!("{} {}", h.flag, h.name);
            let addr = h.addr.as_deref().unwrap_or(&h.fqdn);
            Link {
                uri: vless_uri(&user.uuid, addr, &h.pbk, &h.sni, &h.sid, &label),
                label,
                flag: h.flag.clone(),
                name: h.name.clone(),
                host: h.name.clone(),
            }
        })
        .collect()
}

pub fn blocked_links(n_hosts: usize) -> Vec<Link> {
    let mut names = vec!["blocked".to_string(); n_hosts];
    names.push("t.me/wiybaa to renew".to_string());
    names
        .into_iter()
        .map(|name| {
            let label = format!("⚠️ {name}");
            Link {
                uri: vless_uri(
                    "00000000-0000-0000-0000-000000000000",
                    "0.0.0.0",
                    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                    "example.com",
                    "00000000",
                    &label,
                ),
                label,
                flag: "⚠️".to_string(),
                name,
                host: String::new(),
            }
        })
        .collect()
}
