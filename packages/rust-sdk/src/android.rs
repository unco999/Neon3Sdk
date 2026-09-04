//! Android transport: locate a device, `adb forward`, wait for the headless
//! host, and shut it down cleanly.

use crate::client::{ClientOptions, NeonClient};
use std::process::Command;
use std::time::{Duration, Instant};

pub const ANDROID_HOST_ENDPOINT: &str = "127.0.0.1:43100";
pub const ANDROID_HOST_PORT: u16 = 43100;

#[derive(Debug, Clone)]
pub struct AndroidConfig {
    /// adb executable path; defaults to ANDROID_HOME/platform-tools/adb.
    pub adb: Option<String>,
    /// device serial (e.g. emulator-5554); defaults to the first connected.
    pub device: Option<String>,
    /// use `adb forward tcp:43100 tcp:43100` (loopback). Default true.
    pub use_forward: bool,
    /// direct device IP when not using adb forward.
    pub host: Option<String>,
    /// host port when not using adb forward. Default 43100.
    pub port: u16,
    /// wait budget for the host to become healthy (seconds).
    pub timeout_seconds: f64,
}

impl Default for AndroidConfig {
    fn default() -> Self {
        Self {
            adb: None,
            device: None,
            use_forward: true,
            host: None,
            port: ANDROID_HOST_PORT,
            timeout_seconds: 15.0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct AndroidSessionHandle {
    pub endpoint: String,
    pub device: String,
    pub use_forward: bool,
}

pub struct AndroidSession {
    config: AndroidConfig,
    endpoint: String,
    device: String,
    forward_active: bool,
    stopped: bool,
}

fn resolve_adb(config: &AndroidConfig) -> Result<String, String> {
    if let Some(adb) = &config.adb {
        if std::path::Path::new(adb).is_file() {
            return Ok(adb.clone());
        }
        return Err(format!("adb not found at {adb}"));
    }
    if let Ok(sdk) = std::env::var("ANDROID_HOME") {
        let exe = if cfg!(windows) { "adb.exe" } else { "adb" };
        let candidate = std::path::Path::new(&sdk).join("platform-tools").join(exe);
        if candidate.is_file() {
            return Ok(candidate.to_string_lossy().into_owned());
        }
    }
    Err("adb not found; set AndroidConfig.adb or ANDROID_HOME".into())
}

fn run_adb(adb: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new(adb)
        .args(args)
        .output()
        .map_err(|e| format!("adb {} failed: {e}", args.join(" ")))?;
    if !output.status.success() {
        return Err(format!(
            "adb {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

impl AndroidSession {
    pub fn new(config: AndroidConfig) -> Self {
        Self {
            config,
            endpoint: String::new(),
            device: String::new(),
            forward_active: false,
            stopped: false,
        }
    }

    pub fn endpoint(&self) -> &str {
        &self.endpoint
    }

    /// Locate the device, establish the endpoint, and wait for host health.
    pub fn start(&mut self) -> Result<AndroidSessionHandle, String> {
        let adb = resolve_adb(&self.config)?;
        let use_forward = self.config.use_forward;
        if !use_forward {
            if let Some(host) = &self.config.host {
                self.device = host.clone();
                self.endpoint = format!("{}:{}", host, self.config.port);
            } else {
                return Err("use_forward=false requires AndroidConfig.host".into());
            }
        } else {
            self.device = self.resolve_device(&adb)?;
            run_adb(&adb, &["-s", &self.device, "forward", &format!("tcp:{ANDROID_HOST_PORT}"), &format!("tcp:{ANDROID_HOST_PORT}")])?;
            self.forward_active = true;
            self.endpoint = ANDROID_HOST_ENDPOINT.into();
        }
        self.wait_healthy(&adb)?;
        Ok(AndroidSessionHandle {
            endpoint: self.endpoint.clone(),
            device: self.device.clone(),
            use_forward,
        })
    }

    /// Stop the host cleanly (`service.shutdown`) and remove adb forward.
    pub fn stop(&mut self) {
        if self.stopped {
            return;
        }
        self.stopped = true;
        if let Ok(mut client) = NeonClient::connect(
            ANDROID_HOST_ENDPOINT,
            Some(ClientOptions {
                origin: "neon3-rust-android".into(),
                kind: "cli".into(),
                timeout: Duration::from_secs(3),
                allow_non_loopback: true,
                ..Default::default()
            }),
        ) {
            let _ = client.call("wgpu-runtime", "service.shutdown", serde_json::json!({}));
        }
        if self.forward_active {
            if let Ok(adb) = resolve_adb(&self.config) {
                let _ = run_adb(&adb, &["-s", &self.device, "forward", "--remove", &format!("tcp:{ANDROID_HOST_PORT}")]);
            }
            self.forward_active = false;
        }
    }

    fn resolve_device(&self, adb: &str) -> Result<String, String> {
        let output = run_adb(adb, &["devices"])?;
        let devices: Vec<String> = output
            .lines()
            .skip(1)
            .filter(|line| !line.ends_with("offline") && !line.ends_with("unauthorized"))
            .filter_map(|line| line.split_whitespace().next())
            .map(String::from)
            .collect();
        if let Some(device) = &self.config.device {
            if !devices.contains(device) {
                return Err(format!("adb device {device} is not connected"));
            }
            return Ok(device.clone());
        }
        if devices.is_empty() {
            return Err("no adb devices found; start an emulator or connect a device".into());
        }
        Ok(devices[0].clone())
    }

    fn wait_healthy(&self, _adb: &str) -> Result<(), String> {
        let deadline = Instant::now() + Duration::from_secs_f64(self.config.timeout_seconds);
        let mut last_error: Option<String> = None;
        while Instant::now() < deadline {
            match NeonClient::connect(
                &self.endpoint,
                Some(ClientOptions {
                    origin: "neon3-rust-android".into(),
                    kind: "cli".into(),
                    timeout: Duration::from_secs(1),
                    allow_non_loopback: true,
                    ..Default::default()
                }),
            ) {
                Ok(mut client) => match client.health("wgpu-runtime") {
                    Ok(health) if health.get("status").and_then(|v| v.as_str()) == Some("healthy") => return Ok(()),
                    Ok(_) => last_error = Some("host not healthy yet".into()),
                    Err(e) => last_error = Some(e),
                },
                Err(e) => last_error = Some(e),
            }
            std::thread::sleep(Duration::from_millis(150));
        }
        Err(format!(
            "Timed out waiting for Neon3 Android host at {}: {}",
            self.endpoint,
            last_error.unwrap_or_else(|| "no attempts".into())
        ))
    }
}

impl Drop for AndroidSession {
    fn drop(&mut self) {
        self.stop();
    }
}
