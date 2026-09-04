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

#ifdef __cplusplus
}
#endif

#endif /* NEON3_C_H */
