use std::collections::BTreeMap;
use std::path::Path;

use anyhow::Result;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Default, Serialize, Deserialize)]
pub struct Traffic {
    pub up: u64,
    pub down: u64,
}

impl Traffic {
    pub fn total(&self) -> u64 {
        self.up + self.down
    }
}

#[derive(Clone, Default, Serialize, Deserialize)]
pub struct Usage {
    pub users: BTreeMap<String, Traffic>,
    #[serde(default)]
    pub seen: BTreeMap<String, u64>,
    #[serde(default)]
    pub online: Vec<String>,
    pub collected_at: u64,
}

pub fn load<T: DeserializeOwned + Default>(dir: &Path, name: &str) -> T {
    std::fs::read(dir.join(name))
        .ok()
        .and_then(|data| serde_json::from_slice(&data).ok())
        .unwrap_or_default()
}

pub fn save<T: Serialize>(dir: &Path, name: &str, value: &T) -> Result<()> {
    std::fs::create_dir_all(dir)?;
    let tmp = dir.join(format!("{name}.tmp"));
    std::fs::write(&tmp, serde_json::to_vec(value)?)?;
    std::fs::rename(tmp, dir.join(name))?;
    Ok(())
}
