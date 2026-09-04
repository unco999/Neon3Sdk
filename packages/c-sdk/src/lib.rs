//! C ABI for the Neon3 control-plane protocol.
//!
//! Design rules:
//! - Opaque handle (`neon3_client`) wraps the Rust core behind a mutex so
//!   concurrent FFI calls are safe.
//! - All functions return 0 on success and a stable error code otherwise;
//!   a human-readable message is returned through `out_error` when provided.
//! - Strings returned through `out_*` are allocated by this library and must
//!   be freed with `neon3_free_string`.
//! - No Rust types leak across the boundary; only C-compatible types.
//! - The C ABI talks the wire contract directly (not the Rust facade types),
//!   so the opaque handle stays movable behind the mutex.

use neon3_sdk::NeonClient;
use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_int};
use std::sync::Mutex;

/// Opaque client handle. The wrapped client is protected by a mutex so FFI
/// callers may share the handle across threads.
pub struct neon3_client {
    client: Mutex<NeonClient>,
}

/// Stable error codes (positive values; 0 = success).
pub const NEON3_OK: c_int = 0;
pub const NEON3_ERR_INVALID_ARG: c_int = 1;
pub const NEON3_ERR_CONNECT: c_int = 2;
pub const NEON3_ERR_RPC: c_int = 3;
pub const NEON3_ERR_MEMORY: c_int = 4;
pub const NEON3_ERR_SURFACE: c_int = 5;
pub const NEON3_ERR_UI: c_int = 6;
pub const NEON3_ERR_NULL_POINTER: c_int = 7;

/// Returns a malloc-freeable copy of `s` for FFI consumers.
fn c_string(s: &str) -> *mut c_char {
    match CString::new(s) {
        Ok(c) => c.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

/// Writes a C string into `*out` (must be freed with neon3_free_string).
unsafe fn set_out(out: *mut *mut c_char, s: &str) {
    if !out.is_null() {
        *out = c_string(s);
    }
}

/// Interprets a nullable C string parameter as a Rust `&str`.
unsafe fn param_str<'a>(value: *const c_char) -> Result<&'a str, c_int> {
    if value.is_null() {
        return Err(NEON3_ERR_NULL_POINTER);
    }
    let bytes = CStr::from_ptr(value).to_bytes();
    std::str::from_utf8(bytes).map_err(|_| NEON3_ERR_INVALID_ARG)
}

/// Sets `*out_error` to the message (if provided) and returns the error code.
unsafe fn fail(code: c_int, message: &str, out_error: *mut *mut c_char) -> c_int {
    set_out(out_error, message);
    code
}

/// Helper: lock the client mutex and run a closure that performs an RPC.
fn with_client<T>(
    client: *mut neon3_client,
    f: impl FnOnce(&mut NeonClient) -> Result<T, String>,
) -> Result<T, (c_int, String)> {
    let handle = unsafe { client.as_ref() }.ok_or((NEON3_ERR_NULL_POINTER, "client is null".into()))?;
    let mut guard = handle.client.lock().map_err(|_| (NEON3_ERR_RPC, "client lock poisoned".into()))?;
    f(&mut guard).map_err(|e| (NEON3_ERR_RPC, e))
}

/// Creates a client handle. `endpoint` is `host:port`; `allow_non_loopback`
/// relaxes the default loopback-only policy. Returns 0 on success.
#[no_mangle]
pub unsafe extern "C" fn neon3_client_new(
    endpoint: *const c_char,
    allow_non_loopback: c_int,
    timeout_ms: u64,
    out_client: *mut *mut neon3_client,
    out_error: *mut *mut c_char,
) -> c_int {
    let endpoint = match unsafe { param_str(endpoint) } {
        Ok(s) => s,
        Err(code) => return unsafe { fail(code, "endpoint must be a C string", out_error) },
    };
    let options = neon3_sdk::ClientOptions {
        origin: "neon3-c".into(),
        kind: "cli".into(),
        timeout: std::time::Duration::from_millis(timeout_ms.max(1)),
        allow_non_loopback: allow_non_loopback != 0,
        ..Default::default()
    };
    match NeonClient::connect(endpoint, Some(options)) {
        Ok(client) => {
            if out_client.is_null() {
                return unsafe { fail(NEON3_ERR_NULL_POINTER, "out_client must not be null", out_error) };
            }
            let handle = Box::new(neon3_client { client: Mutex::new(client) });
            *out_client = Box::into_raw(handle);
            NEON3_OK
        }
        Err(e) => unsafe { fail(NEON3_ERR_CONNECT, &format!("connect failed: {e}"), out_error) },
    }
}

/// Frees a client handle created by neon3_client_new.
#[no_mangle]
pub unsafe extern "C" fn neon3_client_free(client: *mut neon3_client) {
    if !client.is_null() {
        drop(Box::from_raw(client));
    }
}

/// Frees a string returned by this library.
#[no_mangle]
pub unsafe extern "C" fn neon3_free_string(value: *mut c_char) {
    if !value.is_null() {
        drop(CString::from_raw(value));
    }
}

/// Performs a generic RPC. `params_json` must be a JSON object. The result
/// JSON is returned through `out_result` (free with neon3_free_string).
#[no_mangle]
pub unsafe extern "C" fn neon3_client_call(
    client: *mut neon3_client,
    target: *const c_char,
    method: *const c_char,
    params_json: *const c_char,
    out_result: *mut *mut c_char,
    out_error: *mut *mut c_char,
) -> c_int {
    let target = match unsafe { param_str(target) } {
        Ok(s) => s.to_owned(),
        Err(code) => return unsafe { fail(code, "target must be a C string", out_error) },
    };
    let method = match unsafe { param_str(method) } {
        Ok(s) => s.to_owned(),
        Err(code) => return unsafe { fail(code, "method must be a C string", out_error) },
    };
    let params = if params_json.is_null() {
        serde_json::Value::Null
    } else {
        match unsafe { param_str(params_json) } {
            Ok(s) => match serde_json::from_str(s) {
                Ok(v) => v,
                Err(_) => return unsafe { fail(NEON3_ERR_INVALID_ARG, "params_json must be valid JSON", out_error) },
            },
            Err(code) => return unsafe { fail(code, "params_json must be a C string", out_error) },
        }
    };
    match with_client(client, |inner| inner.call(&target, &method, params).and_then(|r| r.ok().map_err(|f| f.to_string()))) {
        Ok(result) => {
            let json = serde_json::to_string(&result).unwrap_or_else(|_| "null".into());
            unsafe { set_out(out_result, &json) };
            NEON3_OK
        }
        Err((code, message)) => unsafe { fail(code, &message, out_error) },
    }
}

/// Health probe: returns 1 when healthy, 0 otherwise.
#[no_mangle]
pub unsafe extern "C" fn neon3_client_health(
    client: *mut neon3_client,
    target: *const c_char,
    out_healthy: *mut c_int,
    out_error: *mut *mut c_char,
) -> c_int {
    if out_healthy.is_null() {
        return unsafe { fail(NEON3_ERR_NULL_POINTER, "out_healthy must not be null", out_error) };
    }
    let target = match unsafe { param_str(target) } {
        Ok(s) => s.to_owned(),
        Err(code) => return unsafe { fail(code, "target must be a C string", out_error) },
    };
    match with_client(client, |inner| inner.health(&target)) {
        Ok(h) => {
            let healthy = h.get("status").and_then(|v| v.as_str()) == Some("healthy");
            *out_healthy = if healthy { 1 } else { 0 };
            NEON3_OK
        }
        Err((code, message)) => unsafe { fail(code, &message, out_error) },
    }
}

/// Mounts a NUI Flow source (ui.flow.submit) and returns the program JSON.
#[no_mangle]
pub unsafe extern "C" fn neon3_ui_mount_flow(
    client: *mut neon3_client,
    source: *const c_char,
    out_program: *mut *mut c_char,
    out_error: *mut *mut c_char,
) -> c_int {
    let source = match unsafe { param_str(source) } {
        Ok(s) => s.to_owned(),
        Err(code) => return unsafe { fail(code, "source must be a C string", out_error) },
    };
    let result = with_client(client, |inner| {
        inner.call("wgpu-runtime", "ui.flow.submit", serde_json::json!({"source": source}))
            .and_then(|r| r.ok().map_err(|f| f.to_string()))
    });
    match result {
        Ok(program) => {
            let surface_id = program.get("surface_id").and_then(|v| v.as_str()).unwrap_or("");
            let revision = program.pointer("/program_revision/revision").and_then(|v| v.as_u64()).unwrap_or(0);
            let json = serde_json::json!({"surface_id": surface_id, "program_revision": revision}).to_string();
            unsafe { set_out(out_program, &json) };
            NEON3_OK
        }
        Err((code, message)) => unsafe { fail(code, &message, out_error) },
    }
}

/// Opens a shared surface and returns its generation.
#[no_mangle]
pub unsafe extern "C" fn neon3_surface_open(
    client: *mut neon3_client,
    surface_id: *const c_char,
    width: u32,
    height: u32,
    buffer_count: u32,
    out_generation: *mut i64,
    out_error: *mut *mut c_char,
) -> c_int {
    if out_generation.is_null() {
        return unsafe { fail(NEON3_ERR_NULL_POINTER, "out_generation must not be null", out_error) };
    }
    let surface_id = match unsafe { param_str(surface_id) } {
        Ok(s) => s.to_owned(),
        Err(code) => return unsafe { fail(code, "surface_id must be a C string", out_error) },
    };
    let result = with_client(client, |inner| {
        inner.call(
            "wgpu-runtime",
            "render.surface.open",
            serde_json::json!({
                "session_id": "neon3-c",
                "surface_id": surface_id,
                "kind": "screen_ui",
                "size": {"width": width, "height": height},
                "format": "rgba8unorm",
                "color_space": "srgb",
                "depth": false,
                "buffer_count": buffer_count.max(1),
            }),
        ).and_then(|r| r.ok().map_err(|f| f.to_string()))
    });
    match result {
        Ok(descriptor) => {
            *out_generation = descriptor.get("generation").and_then(|v| v.as_i64()).unwrap_or(-1);
            NEON3_OK
        }
        Err((code, message)) => unsafe { fail(code, &message, out_error) },
    }
}

/// Saves the latest completed frame of a shared surface to a PNG file.
#[no_mangle]
pub unsafe extern "C" fn neon3_surface_save_png(
    client: *mut neon3_client,
    surface_id: *const c_char,
    path: *const c_char,
    out_error: *mut *mut c_char,
) -> c_int {
    let surface_id = match unsafe { param_str(surface_id) } {
        Ok(s) => s.to_owned(),
        Err(code) => return unsafe { fail(code, "surface_id must be a C string", out_error) },
    };
    let path = match unsafe { param_str(path) } {
        Ok(s) => s.to_owned(),
        Err(code) => return unsafe { fail(code, "path must be a C string", out_error) },
    };
    let result = with_client(client, |inner| {
        inner.call(
            "wgpu-runtime",
            "render.surface.capture_png",
            serde_json::json!({"surface_id": surface_id, "path": path}),
        ).and_then(|r| r.ok().map_err(|f| f.to_string()))
    });
    match result {
        Ok(_) => NEON3_OK,
        Err((code, message)) => unsafe { fail(code, &message, out_error) },
    }
}

/// Requests a clean runtime shutdown.
#[no_mangle]
pub unsafe extern "C" fn neon3_client_shutdown(
    client: *mut neon3_client,
    out_error: *mut *mut c_char,
) -> c_int {
    let result = with_client(client, |inner| {
        inner.call("wgpu-runtime", "service.shutdown", serde_json::json!({}))
            .and_then(|r| r.ok().map_err(|f| f.to_string()))
    });
    match result {
        Ok(_) => NEON3_OK,
        Err((code, message)) => unsafe { fail(code, &message, out_error) },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn error_codes_are_stable() {
        assert_eq!(NEON3_OK, 0);
        assert_eq!(NEON3_ERR_NULL_POINTER, 7);
    }
}
