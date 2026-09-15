# Neon3 C SDK

C ABI client library for the Neon3 control-plane protocol. Built as a
`cdylib` (DLL) + `staticlib` (static lib) from Rust, so it links cleanly
from any C/C++ project.

## Files

```
include/neon3.h    ← public C header (single header, no other includes needed)
src/lib.rs         ← Rust FFI implementation (cdylib + staticlib)
Cargo.toml
```

## Build (from source)

Requires Rust toolchain (stable, edition 2021):

```bash
cd packages/c-sdk
cargo build --release
```

Outputs:
- Windows: `target/release/neon3_c.dll` + `neon3_c.dll.lib`
- Linux: `target/release/libneon3_c.so`
- macOS: `target/release/libneon3_c.dylib`

## Release packaging (Windows x86_64)

To produce a distributable release zip:

```powershell
# 1. Build release
cd D:\Neon3Sdk\packages\c-sdk
cargo build --release

# 2. Stage release files
$stage = "D:\Neon3Sdk\release\neon3-c-sdk-v0.1.6"
New-Item -ItemType Directory -Force -Path $stage
Copy-Item include\neon3.h $stage\
Copy-Item target\release\neon3_c.dll $stage\
Copy-Item target\release\neon3_c.dll.lib $stage\

# 3. Zip
Compress-Archive -Path "$stage\*" -DestinationPath "D:\Neon3Sdk\release\neon3-c-sdk-windows-x86_64-v0.1.6.zip" -Force
```

Upload `neon3-c-sdk-windows-x86_64-v0.1.6.zip` to the GitHub release.

## Quick start

```c
#include "neon3.h"
#include <stdio.h>

int main(void) {
    char* err = NULL;
    neon3_client* client = NULL;
    int rc = neon3_client_new("127.0.0.1:39102", 0, 5000, &client, &err);
    if (rc != NEON3_OK) { fprintf(stderr, "connect: %s\n", err); return 1; }

    /* Mount a flow */
    char* program = NULL;
    neon3_ui_mount_flow(client, "flow { root: button { id: btn } }", &program, &err);

    /* Set shader view_extras (v0.2.7) */
    float extras[10][4] = {0};
    extras[0][0] = 1.0f;
    neon3_view_set_extras(client, extras, &err);

    /* Animation control (v0.2.10) */
    neon3_animation_seek(client, "hero.timeline", 0.5f, &err);

    /* Event subscription (shader.event) */
    neon3_event_subscription* sub = NULL;
    neon3_event_subscribe("127.0.0.1:39101", NEON3_EVENT_SHADER_EVENT, &sub, &err);
    char* event_json = NULL;
    if (neon3_event_recv(sub, 1000, &event_json, &err) == NEON3_OK) {
        printf("%s\n", event_json);
        neon3_free_string(event_json);
    }
    neon3_event_subscription_free(sub);

    neon3_client_free(client);
    return 0;
}
```

## Constants (from neon3.h)

```c
#define NEON3_SERVICE_WGPU_RUNTIME   "wgpu-runtime"
#define NEON3_METHOD_WGPU_SET_VIEW_EXTRAS "wgpu.ui.set_view_extras"
#define NEON3_EVENT_SHADER_EVENT    "shader.event"
```

## Error codes

```c
enum {
  NEON3_OK = 0,
  NEON3_ERR_INVALID_ARG = 1,
  NEON3_ERR_CONNECT = 2,
  NEON3_ERR_RPC = 3,
  NEON3_ERR_MEMORY = 4,
  NEON3_ERR_SURFACE = 5,
  NEON3_ERR_UI = 6,
  NEON3_ERR_NULL_POINTER = 7
};
```

## Testing

```bash
cargo test
```

## Version

- SDK 0.1.6 → runtime v0.2.10
