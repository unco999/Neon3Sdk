#ifndef NEON3_C_H
#define NEON3_C_H

/* Neon3 C SDK: control-plane protocol client.
 * All functions return 0 on success and a stable error code otherwise.
 * Strings returned through out_* must be freed with neon3_free_string.
 */

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32)
#  if defined(NEON3_C_STATIC)
#    define NEON3_API
#  elif defined(NEON3_C_BUILD)
#    define NEON3_API __declspec(dllexport)
#  else
#    define NEON3_API __declspec(dllimport)
#  endif
#else
#  define NEON3_API __attribute__((visibility("default")))
#endif

/* Opaque client handle. */
typedef struct neon3_client neon3_client;

/* Opaque event subscription handle (long-lived eventd connection). */
typedef struct neon3_event_subscription neon3_event_subscription;

/* Stable error codes. */
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

/* -------------------------------------------------------------------------
 * Canonical wire constants. Use these instead of hard-coding strings; the
 * compiler will catch a typo and your IDE will autocomplete.
 * ------------------------------------------------------------------------- */

/* Service target names. */
#define NEON3_SERVICE_EVENTD        "eventd"
#define NEON3_SERVICE_UI_RUNTIME    "ui-runtime"
#define NEON3_SERVICE_WGPU_RUNTIME   "wgpu-runtime"

/* RPC method names. */
#define NEON3_METHOD_SERVICE_HEALTH              "service.health"
#define NEON3_METHOD_SERVICE_DESCRIBE             "service.describe"
#define NEON3_METHOD_SERVICE_SHUTDOWN            "service.shutdown"
#define NEON3_METHOD_UI_FLOW_SUBMIT               "ui.flow.submit"
#define NEON3_METHOD_UI_HOST_INBOUND              "ui.host.inbound"
#define NEON3_METHOD_UI_INPUT_FRAME               "ui.input.frame"
#define NEON3_METHOD_UI_HOST_POINTER_EVENT       "ui.host.pointer_event"
#define NEON3_METHOD_RENDER_SURFACE_OPEN          "render.surface.open"
#define NEON3_METHOD_RENDER_SURFACE_ACQUIRE       "render.surface.acquire"
#define NEON3_METHOD_RENDER_SURFACE_FRAME         "render.surface.frame"
#define NEON3_METHOD_RENDER_SURFACE_CAPTURE_PNG   "render.surface.capture_png"
#define NEON3_METHOD_WGPU_SET_VIEW_EXTRAS        "wgpu.ui.set_view_extras"
#define NEON3_METHOD_WGPU_ANIMATION_PREFIX        "wgpu.ui.animation."

/* Event names on eventd. */
#define NEON3_EVENT_SHADER_EVENT       "shader.event"
#define NEON3_EVENT_FILE_DROP_ACCEPTED "ui.file_drop.accepted"
#define NEON3_EVENT_CLICK_BLANK       "ui.click_blank"

/* Create a client. endpoint is "host:port"; allow_non_loopback relaxes the
 * default loopback-only policy. Returns 0 on success. */
NEON3_API int neon3_client_new(const char* endpoint, int allow_non_loopback,
                               uint64_t timeout_ms, neon3_client** out_client,
                               char** out_error);

/* Free a client handle. */
NEON3_API void neon3_client_free(neon3_client* client);

/* Free a string returned by this library. */
NEON3_API void neon3_free_string(char* value);

/* Generic RPC. params_json must be a JSON object (or NULL for {}). The result
 * JSON is returned through out_result. */
NEON3_API int neon3_client_call(neon3_client* client, const char* target,
                                const char* method, const char* params_json,
                                char** out_result, char** out_error);

/* Health probe: sets *out_healthy to 1 when the target is healthy. */
NEON3_API int neon3_client_health(neon3_client* client, const char* target,
                                  int* out_healthy, char** out_error);

/* Mount a NUI Flow source (ui.flow.submit). Returns program JSON. */
NEON3_API int neon3_ui_mount_flow(neon3_client* client, const char* source,
                                  char** out_program, char** out_error);

/* Open a shared surface; returns its generation via out_generation. */
NEON3_API int neon3_surface_open(neon3_client* client, const char* surface_id,
                                 uint32_t width, uint32_t height,
                                 uint32_t buffer_count, int64_t* out_generation,
                                 char** out_error);

/* Save the latest completed frame of a shared surface to a PNG file. */
NEON3_API int neon3_surface_save_png(neon3_client* client,
                                     const char* surface_id, const char* path,
                                     char** out_error);

/* Request a clean runtime shutdown. */
NEON3_API int neon3_client_shutdown(neon3_client* client, char** out_error);

/* -------------------------------------------------------------------------
 * v0.2.7: shader view_extras uniform upload.
 * ------------------------------------------------------------------------- */

/* Upload 10 rows of vec4 to the shader's view.extras[0..9] uniform
 * (wgpu.ui.set_view_extras). extras must point to 10 rows of 4 floats. */
NEON3_API int neon3_view_set_extras(neon3_client* client,
                                    const float extras[10][4],
                                    char** out_error);

/* -------------------------------------------------------------------------
 * v0.2.10: renderer-owned animation timeline control.
 * ------------------------------------------------------------------------- */

/* Pause a renderer-owned animation timeline identified by node_path. */
NEON3_API int neon3_animation_pause(neon3_client* client,
                                    const char* node_path,
                                    char** out_error);

/* Resume a paused animation timeline. */
NEON3_API int neon3_animation_resume(neon3_client* client,
                                     const char* node_path,
                                     char** out_error);

/* Cancel an animation timeline. */
NEON3_API int neon3_animation_cancel(neon3_client* client,
                                      const char* node_path,
                                      char** out_error);

/* Seek an animation timeline to progress in [0.0, 1.0]. */
NEON3_API int neon3_animation_seek(neon3_client* client,
                                   const char* node_path, float progress,
                                   char** out_error);

/* -------------------------------------------------------------------------
 * v0.2.7: eventd subscription (for shader.event and other bus events).
 * ------------------------------------------------------------------------- */

/* Subscribe to events named `name` on eventd (default 127.0.0.1:39101).
 * out_sub receives an opaque handle; free it with
 * neon3_event_subscription_free. */
NEON3_API int neon3_event_subscribe(const char* endpoint,
                                    const char* name,
                                    neon3_event_subscription** out_sub,
                                    char** out_error);

/* Block until one delivery frame arrives (or timeout_ms elapses). The event
 * JSON envelope is returned through out_event_json (free with
 * neon3_free_string). Returns NEON3_ERR_RPC with a timeout message on expiry. */
NEON3_API int neon3_event_recv(neon3_event_subscription* sub,
                               uint64_t timeout_ms,
                               char** out_event_json,
                               char** out_error);

/* Free an event subscription handle. */
NEON3_API void neon3_event_subscription_free(neon3_event_subscription* sub);

#ifdef __cplusplus
}
#endif

#endif /* NEON3_C_H */
