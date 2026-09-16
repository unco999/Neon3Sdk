#include "neon3.hpp"
#include <cstdio>
#include <chrono>
#include <thread>
int main() {
  neon3::Client client("127.0.0.1:43123", false);
  bool ok = client.health();
  std::string flow = "version 1\nsurface a revision 1\nsurface root column\n  text t value \"hi\"\n";
  std::string p = client.mountFlow(flow);
  int64_t g = client.openSurface("a", 1280, 720, 2);
  // headless renderers complete the first frame asynchronously; wait like the C ABI e2e.
  std::this_thread::sleep_for(std::chrono::milliseconds(1500));
  client.savePng("a", "out.png");

  // Editor document APIs (editor-runtime, v0.2.10+). Requires a host that
  // serves the editor-runtime service on the same connection (e.g. the
  // Android host); the desktop headless wgpu server answers with an
  // unsupported/unknown-target error, which still exercises the full
  // wrapper -> C ABI -> wire path.
  try {
    neon3::EditorClient editor(client);
    std::string opened = editor.open("doc-1", "sess-1", flow, "nui_flow");
    std::string snap = editor.snapshot("doc-1", "sess-1", 1);
    const char* changeset = "{\"base_revision\":0,"
                            "\"ops\":[{\"kind\":\"insert\",\"line\":2,\"column\":6,"
                            "\"end\":{\"line\":2,\"column\":7},\"text\":\"!\"}]}";
    std::string applied = editor.applyChange("doc-1", "sess-1", 1, changeset, "commit");
    std::string comps = editor.completions("doc-1", "sess-1", 1, 1, 2, 6, "automatic");
    std::string closed = editor.close("doc-1", "sess-1", 1);
    std::printf("editor opened=%s applied=%s comps=%s closed=%s\n",
                opened.c_str(), applied.c_str(), comps.c_str(), closed.c_str());
  } catch (const neon3::Error& e) {
    std::printf("editor: rejected by server (expected without editor-runtime host): %s\n", e.what());
  }

  // Eventd subscription (v0.2.7+): needs the eventd daemon on 39101.
  try {
    neon3::EventSubscription sub("127.0.0.1:39101", "shader.event");
    std::printf("event subscription established\n");
    (void)sub;  // recv blocks; exercised by the caller when a runtime is live
  } catch (const neon3::Error& e) {
    std::printf("eventd: unavailable (expected when eventd is not running): %s\n", e.what());
  }

  client.shutdown();
  std::printf("ok=%d g=%lld program=%s\n", ok, (long long)g, p.c_str());
  return 0;
}
