#include "neon3.hpp"
#include <cstdio>
int main() {
  neon3::Client client("127.0.0.1:43100", false);
  bool ok = client.health();
  std::string flow = "version 1\nsurface a revision 1\nsurface root column\n  text t value \"hi\"\n";
  std::string p = client.mountFlow(flow);
  int64_t g = client.openSurface("a", 1280, 720, 2);
  client.savePng("a", "out.png");

  // Editor document APIs (editor-runtime, v0.2.10+).
  neon3::EditorClient editor(client);
  std::string opened = editor.open("doc-1", "sess-1", flow, "nui_flow");
  std::string snap = editor.snapshot("doc-1", "sess-1", 1);
  const char* changeset = "{\"base_revision\":0,"
                          "\"ops\":[{\"kind\":\"insert\",\"line\":2,\"column\":6,"
                          "\"end\":{\"line\":2,\"column\":7},\"text\":\"!\"}]}";
  std::string applied = editor.applyChange("doc-1", "sess-1", 1, changeset, "commit");
  std::string comps = editor.completions("doc-1", "sess-1", 1, 1, 2, 6, "automatic");
  std::string closed = editor.close("doc-1", "sess-1", 1);

  // Eventd subscription (v0.2.7+): subscribe for shader events.
  neon3::EventSubscription sub("127.0.0.1:39101", "shader.event");
  (void)sub;  // recv blocks; exercised by the caller when a runtime is live

  client.shutdown();
  std::printf("ok=%d g=%lld program=%s\n", ok, (long long)g, p.c_str());
  std::printf("editor opened=%s applied=%s comps=%s closed=%s\n",
              opened.c_str(), applied.c_str(), comps.c_str(), closed.c_str());
  return 0;
}
