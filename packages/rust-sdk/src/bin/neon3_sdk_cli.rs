//! Rust SDK RPC diagnostics CLI. This is not the project-level `neon3-sdk`
//! Python development/lifecycle CLI.

use neon3_sdk::{ClientOptions, NeonClient, NuiFlowError, UiSession, UiTarget};
use neon3_sdk::constants::{method, service};
use serde_json::{json, Value};
use std::time::Duration;

const USAGE: &str = "Usage: neon3-rust-sdk [--endpoint HOST:PORT] [--target TARGET] [--timeout-ms N] <health|describe|snapshot|compile FILE|help>";

#[derive(Debug)]
struct Args { endpoint: String, target: String, timeout: Duration, command: String, file: Option<String> }

fn parse_args(raw: &[String]) -> Result<Args, String> {
    let mut endpoint = "127.0.0.1:39102".to_string();
    let mut target = service::UI_RUNTIME.to_string();
    let mut timeout = Duration::from_secs(10);
    let mut positional = Vec::new();
    let mut i = 0;
    while i < raw.len() {
        match raw[i].as_str() {
            "--endpoint" => { i += 1; endpoint = raw.get(i).ok_or("--endpoint requires HOST:PORT")?.clone(); }
            "--target" => { i += 1; target = raw.get(i).ok_or("--target requires a service target")?.clone(); }
            "--timeout-ms" => { i += 1; let ms: u64 = raw.get(i).ok_or("--timeout-ms requires N")?.parse().map_err(|_| "--timeout-ms must be an integer")?; if ms == 0 { return Err("--timeout-ms must be greater than zero".into()); } timeout = Duration::from_millis(ms); }
            arg if arg.starts_with('-') => return Err(format!("unknown option {arg}")),
            arg => positional.push(arg.to_string()),
        }
        i += 1;
    }
    let command = positional.first().cloned().unwrap_or_else(|| "help".into());
    let file = positional.get(1).cloned();
    if command == "compile" && file.is_none() { return Err("compile requires FILE or -".into()); }
    if positional.len() > 2 { return Err("too many positional arguments".into()); }
    Ok(Args { endpoint, target, timeout, command, file })
}

fn client(args: &Args) -> Result<NeonClient, String> {
    NeonClient::connect(&args.endpoint, Some(ClientOptions { timeout: args.timeout, origin: "neon3-cli".into(), ..Default::default() }))
}

fn run(args: Args) -> Result<Value, String> {
    if args.command == "help" || args.command == "--help" { return Ok(json!({"status":"ok","usage":USAGE,"commands":["health","describe","snapshot","compile"]})); }
    let mut client = client(&args)?;
    match args.command.as_str() {
        "health" => client.call(&args.target, method::SERVICE_HEALTH, json!({}))?.ok().map_err(|e| e.to_string()),
        "describe" => client.call(&args.target, method::SERVICE_DESCRIBE, json!({}))?.ok().map_err(|e| e.to_string()),
        "snapshot" => client.call(&args.target, method::DEBUG_SNAPSHOT_GET, json!({}))?.ok().map_err(|e| e.to_string()),
        "compile" => {
            let path = args.file.as_deref().unwrap();
            let source = if path == "-" { return Err("compile FILE does not accept stdin in this CLI build; pass a file path".into()); } else { std::fs::read_to_string(path).map_err(|e| format!("read {path}: {e}"))? };
            let target = if args.target == service::WGPU_RUNTIME { UiTarget::WgpuRuntime } else { UiTarget::UiRuntime };
            let mut session = UiSession::new(target);
            match session.compile_flow(&mut client, &source) {
                Ok(report) => serde_json::to_value(report).map_err(|e| e.to_string()),
                Err(NuiFlowError::Compile(error)) => Ok(json!({"status":"invalid","code":error.code,"message":error.message,"request_id":error.request_id,"report":error.report,"details":error.details})),
                Err(error) => Err(error.to_string()),
            }
        }
        other => Err(format!("unknown command {other}; {USAGE}")),
    }
}

fn main() {
    let raw: Vec<String> = std::env::args().skip(1).collect();
    let result = parse_args(&raw).and_then(run);
    match result {
        Ok(value) => { println!("{}", serde_json::to_string(&value).unwrap_or_else(|e| json!({"status":"failed","error":e.to_string()}).to_string())); }
        Err(error) => { println!("{}", json!({"status":"failed","error":error,"usage":USAGE})); std::process::exit(1); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn help_is_offline_and_compile_requires_file() {
        let help = parse_args(&["help".into()]).unwrap();
        assert_eq!(help.command, "help");
        assert!(parse_args(&["compile".into()]).is_err());
        assert!(parse_args(&["--timeout-ms".into(), "0".into(), "health".into()]).is_err());
    }
}
