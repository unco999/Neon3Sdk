# Neon3 C++ SDK

Header-only RAII wrapper over the [Neon3 C ABI](../c-sdk/include/neon3.h).
Link against `neon3_c` (DLL or static) and `#include "neon3.hpp"`.

## Files

```
include/neon3.hpp   ← header-only RAII wrapper (no .cpp files needed)
```

## Dependencies

- C++17 compiler
- `neon3_c` library (DLL or staticlib) from the C SDK

## Build

This is a header-only library. Just add the include path:

```cmake
target_include_directories(your_app PRIVATE packages/cpp-sdk/include packages/c-sdk/include)
target_link_libraries(your_app PRIVATE neon3_c)
```

## Quick start

```cpp
#include "neon3.hpp"
#include <cstdio>

int main() {
  neon3::Client client("127.0.0.1:39102");
  if (!client.health()) return 1;

  // Mount a NUI flow
  client.mountFlow("version 1\nroot: button { id: btn }");

  // Set shader view_extras (v0.2.7)
  float extras[10][4] = {{1.0f, 0, 0, 0}};
  client.setViewExtras(extras);

  // Animation control (v0.2.10)
  client.animationSeek("hero.timeline", 0.5f);
  client.animationPause("hero.timeline");

  // Headless editor documents (editor-runtime, v0.2.10+)
  neon3::EditorClient editor(client);
  editor.open("doc-1", "sess-1", flow, "nui_flow");
  std::string snap = editor.snapshot("doc-1", "sess-1", 1);
  const char* changeset = "{\"base_revision\":0,"
                          "\"ops\":[{\"kind\":\"insert\",\"line\":2,\"column\":6,"
                          "\"end\":{\"line\":2,\"column\":7},\"text\":\"!\"}]}";
  editor.applyChange("doc-1", "sess-1", 1, changeset, "commit");
  editor.completions("doc-1", "sess-1", 1, 1, 2, 6, "automatic");
  editor.close("doc-1", "sess-1", 1);

  // Eventd subscription (v0.2.7+): shader.event and other bus events
  neon3::EventSubscription sub("127.0.0.1:39101", "shader.event");
  // std::string evt = sub.recv(5000); // blocks until one frame arrives

  // Offscreen screenshot
  int64_t gen = client.openSurface("hello", 1280, 720);
  client.savePng("hello", "out.png");

  client.shutdown();
  return 0;
}
```

## Release packaging

The C++ SDK is header-only, so the release zip just contains `neon3.hpp`
and the C SDK headers + library:

```powershell
# 1. Build the C SDK first (produces neon3_c.dll + .lib)
cd D:\Neon3Sdk\packages\c-sdk
cargo build --release

# 2. Stage C++ release
$stage = "D:\Neon3Sdk\release\neon3-cpp-sdk-v0.1.6"
New-Item -ItemType Directory -Force -Path $stage
New-Item -ItemType Directory -Force -Path "$stage\include"

Copy-Item packages\cpp-sdk\include\neon3.hpp $stage\include\
Copy-Item packages\c-sdk\include\neon3.h $stage\include\
Copy-Item packages\c-sdk\target\release\neon3_c.dll $stage\
Copy-Item packages\c-sdk\target\release\neon3_c.dll.lib $stage\

# 3. Zip
Compress-Archive -Path "$stage\*" -DestinationPath "D:\Neon3Sdk\release\neon3-cpp-sdk-windows-x86_64-v0.1.6.zip" -Force
```

Upload `neon3-cpp-sdk-windows-x86_64-v0.1.6.zip` to the GitHub release.

## Error handling

All methods throw `neon3::Error` on failure:

```cpp
try {
  client.animationSeek("hero.timeline", 0.5f);
} catch (const neon3::Error& e) {
  fprintf(stderr, "error %d: %s\n", e.code(), e.what());
}
```

## Version

- SDK 0.1.6 → runtime v0.2.10
