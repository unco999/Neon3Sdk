# Neon3 C++ SDK (neon3-cpp)

Header-only RAII wrapper over the [Neon3 C ABI](../c-sdk/include/neon3.h).
Link against `neon3_c` (DLL or static) and `#include "neon3.hpp"`.

```cpp
#include "neon3.hpp"
#include <cstdio>

int main() {
  neon3::Client client("127.0.0.1:43100", /*allow_non_loopback=*/false);
  if (!client.health()) return 1;
  auto program = client.mountFlow("version 1\nsurface a revision 1\nsurface root column\n  text t value \"hi\"\n");
  auto generation = client.openSurface("a", 1280, 720, 2);
  client.savePng("a", "out.png");
  client.shutdown();
  return 0;
}
```
