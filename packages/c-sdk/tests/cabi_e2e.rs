//! End-to-end C ABI test: load the cdylib, exercise the exported C surface
//! against a real Neon3 headless GPU server, and verify the PNG artifact.
//!
//! Requires the neon-wgpu-runtime binary for the server, e.g.:
//!   NEON3_RUNTIME_BIN=D:\Neon3\target\debug\neon-wgpu-runtime.exe
//!   cargo test -p neon3-c --test cabi_e2e -- --nocapture

use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_int};
use std::path::Path;

type NewFn = unsafe extern "C" fn(*const c_char, c_int, u64, *mut *mut std::ffi::c_void, *mut *mut c_char) -> c_int;
type FreeFn = unsafe extern "C" fn(*mut std::ffi::c_void);
type FreeStrFn = unsafe extern "C" fn(*mut c_char);
type CallFn = unsafe extern "C" fn(*mut std::ffi::c_void, *const c_char, *const c_char, *const c_char, *mut *mut c_char, *mut *mut c_char) -> c_int;
type HealthFn = unsafe extern "C" fn(*mut std::ffi::c_void, *const c_char, *mut c_int, *mut *mut c_char) -> c_int;
type MountFn = unsafe extern "C" fn(*mut std::ffi::c_void, *const c_char, *mut *mut c_char, *mut *mut c_char) -> c_int;
type OpenFn = unsafe extern "C" fn(*mut std::ffi::c_void, *const c_char, u32, u32, u32, *mut i64, *mut *mut c_char) -> c_int;
type SavePngFn = unsafe extern "C" fn(*mut std::ffi::c_void, *const c_char, *const c_char, *mut *mut c_char) -> c_int;
type ShutdownFn = unsafe extern "C" fn(*mut std::ffi::c_void, *mut *mut c_char) -> c_int;

unsafe fn cstr(s: &str) -> CString { CString::new(s).unwrap() }
unsafe fn read_str(p: *mut c_char) -> String {
    if p.is_null() { return String::new(); }
    let s = CStr::from_ptr(p).to_string_lossy().into_owned();
    drop(CString::from_raw(p));
    s
}

#[test]
fn cabi_end_to_end() {
    // Locate the runtime server binary.
    let runtime_bin = std::env::var("NEON3_RUNTIME_BIN").unwrap_or_else(|_| {
        "D:\\Neon3\\target\\debug\\neon-wgpu-runtime.exe".into()
    });
    if !Path::new(&runtime_bin).exists() {
        eprintln!("skipping: NEON3_RUNTIME_BIN not found at {runtime_bin}");
        return;
    }
    // Spawn the headless external GPU server.
    let mut server = std::process::Command::new(&runtime_bin)
        .arg("--headless-external-server")
        .arg("127.0.0.1:43123")
        .spawn()
        .expect("spawn server");
    std::thread::sleep(std::time::Duration::from_secs(4));

    // Load the cdylib.
    let lib_path = {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("target").join("debug");
        if cfg!(windows) { dir.join("neon3_c.dll") } else { dir.join("libneon3_c.so") }
    };
    let lib = unsafe { libloading::Library::new(&lib_path) }.unwrap_or_else(|e| panic!("load {}: {e}", lib_path.display()));

    unsafe {
        let new_fn: libloading::Symbol<NewFn> = lib.get(b"neon3_client_new").unwrap();
        let free_fn: libloading::Symbol<FreeFn> = lib.get(b"neon3_client_free").unwrap();
        let free_str: libloading::Symbol<FreeStrFn> = lib.get(b"neon3_free_string").unwrap();
        let health_fn: libloading::Symbol<HealthFn> = lib.get(b"neon3_client_health").unwrap();
        let mount_fn: libloading::Symbol<MountFn> = lib.get(b"neon3_ui_mount_flow").unwrap();
        let open_fn: libloading::Symbol<OpenFn> = lib.get(b"neon3_surface_open").unwrap();
        let save_fn: libloading::Symbol<SavePngFn> = lib.get(b"neon3_surface_save_png").unwrap();
        let shutdown_fn: libloading::Symbol<ShutdownFn> = lib.get(b"neon3_client_shutdown").unwrap();

        // 1. connect
        let endpoint = cstr("127.0.0.1:43123");
        let mut client: *mut std::ffi::c_void = std::ptr::null_mut();
        let mut err: *mut c_char = std::ptr::null_mut();
        let rc = new_fn(endpoint.as_ptr(), 1, 10000, &mut client, &mut err);
        assert_eq!(rc, 0, "connect failed: {}", read_str(err));
        assert!(!client.is_null());

        // 2. health
        let target = cstr("wgpu-runtime");
        let mut healthy: c_int = 0;
        let rc = health_fn(client, target.as_ptr(), &mut healthy, &mut err);
        assert_eq!(rc, 0, "health failed: {}", read_str(err));
        assert_eq!(healthy, 1, "runtime should be healthy");

        // 3. mount flow
        let flow = cstr("version 1\nsurface example revision 1\nsurface root column\n  text title value \"Hello C ABI\"\n");
        let mut program: *mut c_char = std::ptr::null_mut();
        let rc = mount_fn(client, flow.as_ptr(), &mut program, &mut err);
        assert_eq!(rc, 0, "mount flow failed: {}", read_str(err));
        let program_json = read_str(program);
        assert!(program_json.contains("surface_id"), "program: {program_json}");

        // 4. open surface
        let sid = cstr("example");
        let mut generation: i64 = -1;
        let rc = open_fn(client, sid.as_ptr(), 640, 360, 2, &mut generation, &mut err);
        assert_eq!(rc, 0, "open surface failed: {}", read_str(err));
        assert!(generation >= 0, "generation: {generation}");

        // wait for a rendered frame
        std::thread::sleep(std::time::Duration::from_millis(1500));

        // 5. save png
        let png = cstr("cabi-e2e.png");
        let rc = save_fn(client, sid.as_ptr(), png.as_ptr(), &mut err);
        assert_eq!(rc, 0, "save png failed: {}", read_str(err));
        let path = std::path::Path::new("cabi-e2e.png");
        assert!(path.exists(), "PNG artifact missing");
        let bytes = std::fs::read(path).unwrap();
        assert_eq!(&bytes[..8], b"\x89PNG\r\n\x1a\n", "invalid PNG signature");
        let _ = std::fs::remove_file(path);

        // 6. shutdown
        let rc = shutdown_fn(client, &mut err);
        assert_eq!(rc, 0, "shutdown failed: {}", read_str(err));

        free_fn(client);
    }

    let _ = server.wait();
}
