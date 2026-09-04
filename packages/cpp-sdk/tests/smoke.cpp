#include "neon3.hpp"
#include <cstdio>
int main() {
  neon3::Client client("127.0.0.1:43100", false);
  bool ok = client.health();
  std::string flow = "version 1\nsurface a revision 1\nsurface root column\n  text t value \"hi\"\n";
  std::string p = client.mountFlow(flow);
  int64_t g = client.openSurface("a", 1280, 720, 2);
  client.savePng("a", "out.png");
  client.shutdown();
  std::printf("ok=%d g=%lld program=%s\n", ok, (long long)g, p.c_str());
  return 0;
}
