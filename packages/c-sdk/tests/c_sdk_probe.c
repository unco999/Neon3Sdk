/* End-to-end C probe: health -> ui.flow.submit -> surface.open ->
 * surface.save_png -> shutdown against a Neon3 runtime endpoint.
 * Usage: c_sdk_probe <endpoint> [png-path]
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/neon3.h"

static void step(const char* name, int ok, const char* detail) {
  printf("{\"step\":\"%s\",\"ok\":%s%s%s}\n", name, ok ? "true" : "false",
         detail ? "," : "", detail ? detail : "");
}

int main(int argc, char** argv) {
  const char* endpoint = argc > 1 ? argv[1] : "127.0.0.1:43123";
  const char* png = argc > 2 ? argv[2] : "c-sdk-probe.png";
  char* error = NULL;
  int rc;

  neon3_client* client = NULL;
  rc = neon3_client_new(endpoint, 1, 10000, &client, &error);
  if (rc != NEON3_OK || !client) {
    step("connect", 0, error);
    neon3_free_string(error);
    return 1;
  }
  step("connect", 1, NULL);

  int healthy = 0;
  rc = neon3_client_health(client, "wgpu-runtime", &healthy, &error);
  if (rc != NEON3_OK) { step("health", 0, error); neon3_free_string(error); return 1; }
  char detail[64];
  snprintf(detail, sizeof(detail), "\"status\":%s", healthy ? "\"healthy\"" : "\"degraded\"");
  step("health", healthy == 1, detail);

  char* program = NULL;
  const char* flow = "version 1\nsurface example revision 1\nsurface root column\n  text title value \"Hello C SDK\"\n";
  rc = neon3_ui_mount_flow(client, flow, &program, &error);
  if (rc != NEON3_OK) { step("ui.flow.submit", 0, error); neon3_free_string(error); return 1; }
  char prog_detail[128];
  snprintf(prog_detail, sizeof(prog_detail), "\"program\":%s", program);
  step("ui.flow.submit", 1, prog_detail);
  neon3_free_string(program);

  int64_t generation = -1;
  rc = neon3_surface_open(client, "example", 1280, 720, 2, &generation, &error);
  if (rc != NEON3_OK) { step("render.surface.open", 0, error); neon3_free_string(error); return 1; }
  char gen_detail[64];
  snprintf(gen_detail, sizeof(gen_detail), "\"generation\":%lld", (long long)generation);
  step("render.surface.open", generation >= 0, gen_detail);

  /* let the render loop produce a frame */
  {
    double end = 0;
    while (end < 1.5) { volatile double x = 0; for (int i = 0; i < 1000000; ++i) x += 1; end += 0.0005; }
  }

  rc = neon3_surface_save_png(client, "example", png, &error);
  if (rc != NEON3_OK) { step("render.surface.capture_png", 0, error); neon3_free_string(error); return 1; }
  char png_detail[128];
  snprintf(png_detail, sizeof(png_detail), "\"path\":\"%s\"", png);
  step("render.surface.capture_png", 1, png_detail);

  rc = neon3_client_shutdown(client, &error);
  if (rc != NEON3_OK) { step("service.shutdown", 0, error); neon3_free_string(error); }
  else step("service.shutdown", 1, NULL);

  neon3_client_free(client);
  printf("{\"probe\":\"c-sdk\",\"status\":\"passed\"}\n");
  return 0;
}
