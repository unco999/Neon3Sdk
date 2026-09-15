//! React-hooks-style façade over the Rust Neon3 SDK.
//!
//! ```no_run
//! use neon3_sdk::facade::App;
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! let mut app = App::connect("127.0.0.1:39102", "demo")?;
//! app.mount("counter.nui")?;
//!
//! app.state("count", 0)?;
//! app.on("btn.increment", |app, _payload| {
//!     let new = app.get_state("count").as_i64().unwrap_or(0) + 1;
//!     app.set_state("count", new)?;
//!     Ok(())
//! })?;
//!
//! app.anim().animation_seek("hero.timeline", 0.5)?;
//! app.view_extras(&[[1.0, 0.0, 0.0, 0.0]])?;
//! # Ok(())
//! # }
//! ```

use crate::client::{ClientOptions, NeonClient};
use crate::event::EventClient;
use crate::render::RenderClient;
use crate::session::{UiSession, UiTarget};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::sync::Arc;

pub type IntentHandler = Arc<dyn Fn(&mut App, Value) -> Result<(), String> + Send + Sync>;

pub struct App {
    client: NeonClient,
    session: UiSession,
    render: RenderClient,
    events: Option<EventClient>,
    scalars: HashMap<String, Value>,
    intent_handlers: HashMap<String, IntentHandler>,
}

impl App {
    pub fn connect(endpoint: &str, origin: &str) -> Result<Self, String> {
        let options = ClientOptions {
            origin: origin.to_string(),
            kind: "facade".to_string(),
            ..Default::default()
        };
        let client = NeonClient::connect(endpoint, Some(options))?;
        // RenderClient needs its own connection (it targets wgpu-runtime,
        // a different port). The UI session reuses the primary client.
        let render = RenderClient::new(
            NeonClient::connect(endpoint, Some(ClientOptions {
                origin: origin.to_string(),
                kind: "facade-render".to_string(),
                ..Default::default()
            }))?,
            "wgpu-runtime",
        );
        let session = UiSession::new(UiTarget::UiRuntime);
        Ok(Self {
            client,
            session,
            render,
            events: None,
            scalars: HashMap::new(),
            intent_handlers: HashMap::new(),
        })
    }

    pub fn with_events(mut self, eventd_endpoint: &str) -> Self {
        self.events = Some(EventClient::new(eventd_endpoint));
        self
    }

    pub fn mount(&mut self, source: &str) -> Result<(), String> {
        self.session.mount_flow(&mut self.client, source)?;
        Ok(())
    }

    pub fn mount_file<P: AsRef<std::path::Path>>(&mut self, path: P) -> Result<(), String> {
        let source = std::fs::read_to_string(path.as_ref())
            .map_err(|e| format!("read flow file: {e}"))?;
        self.mount(&source)
    }

    pub fn state<T: serde::Serialize>(&mut self, key: &str, initial: T) -> Result<(), String> {
        let v = serde_json::to_value(initial).map_err(|e| format!("serialize state: {e}"))?;
        self.scalars.insert(key.to_string(), v);
        Ok(())
    }

    pub fn get_state(&self, key: &str) -> Value {
        self.scalars.get(key).cloned().unwrap_or(Value::Null)
    }

    pub fn set_state<T: serde::Serialize>(&mut self, key: &str, value: T) -> Result<(), String> {
        let v = serde_json::to_value(value).map_err(|e| format!("serialize state: {e}"))?;
        self.scalars.insert(key.to_string(), v);
        self.publish()
    }

    pub fn on<F>(&mut self, intent: &str, handler: F) -> Result<(), String>
    where
        F: Fn(&mut App, Value) -> Result<(), String> + Send + Sync + 'static,
    {
        self.intent_handlers.insert(intent.to_string(), Arc::new(handler));
        Ok(())
    }

    pub fn dispatch(&mut self, intent: &str, payload: Value) -> Result<(), String> {
        // Clone the handler reference out of the map so we don't hold an
        // immutable borrow of `self` while calling it with `&mut self`.
        let handler = self.intent_handlers.get(intent)
            .cloned()
            .ok_or_else(|| format!("no handler for intent: {intent}"))?;
        handler(self, payload)
    }

    pub fn publish(&mut self) -> Result<(), String> {
        let changes: Vec<Value> = self.scalars.iter()
            .map(|(k, v)| json!({"key": k, "value": v}))
            .collect();
        if changes.is_empty() {
            return Ok(());
        }
        // Split borrow: destructure self so the borrow checker knows
        // `session` and `client` are disjoint fields.
        let App { session, client, .. } = self;
        session.publish(client, &changes)?;
        Ok(())
    }

    /// Upload shader view_extras uniform (v0.2.7).
    pub fn view_extras(&mut self, rows: &[[f32; 4]]) -> Result<Value, String> {
        self.render.set_view_extras(rows)
    }

    /// Animation control façade.
    pub fn anim(&mut self) -> &mut RenderClient {
        &mut self.render
    }

    pub fn run(&mut self) -> Result<(), String> {
        Ok(())
    }
}
