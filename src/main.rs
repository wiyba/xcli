mod agent;
mod cli;
mod config;
mod links;
mod remote;
mod serve;
mod state;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "xcli", version)]
struct Cli {
    #[arg(
        long,
        env = "XCLI_CONFIG",
        default_value = "/run/secrets/xcli.json",
        global = true
    )]
    config: String,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    Agent,
    Serve,
    Ls,
    Status,
    Block { user: String },
    Unblock { user: String },
    Export { user: String },
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let cfg = config::load(&cli.config)?;
    match cli.cmd {
        Cmd::Agent => agent::run(cfg).await,
        Cmd::Serve => serve::run(cfg).await,
        Cmd::Ls => cli::ls(&cfg).await,
        Cmd::Status => cli::status(&cfg).await,
        Cmd::Block { user } => cli::set_blocked(&cfg, &user, true).await,
        Cmd::Unblock { user } => cli::set_blocked(&cfg, &user, false).await,
        Cmd::Export { user } => cli::export(&cfg, &user).await,
    }
}
