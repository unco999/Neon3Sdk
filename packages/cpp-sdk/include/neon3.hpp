// Neon3 C++ SDK: RAII wrapper over the Neon3 C ABI (neon3.h).
// Header-only; link neon3_c (DLL or static) and include this file.
#ifndef NEON3_CPP_SDK_HPP
#define NEON3_CPP_SDK_HPP

#include <cstdint>
#include <stdexcept>
#include <string>
#include <utility>
#include "neon3.h"

namespace neon3 {

class Error : public std::runtime_error {
public:
    explicit Error(int code, const std::string& message)
        : std::runtime_error(message), code_(code) {}
    int code() const noexcept { return code_; }
private:
    int code_;
};

namespace detail {
    inline void check(int rc, char*& error) {
        if (rc != NEON3_OK) {
            std::string message = error ? error : "neon3 error";
            if (error) neon3_free_string(error);
            error = nullptr;
            throw Error(rc, message);
        }
    }
    template <typename T>
    class Ptr {
    public:
        Ptr() = default;
        explicit Ptr(T* p) noexcept : ptr_(p) {}
        ~Ptr() { reset(); }
        Ptr(const Ptr&) = delete;
        Ptr& operator=(const Ptr&) = delete;
        Ptr(Ptr&& other) noexcept : ptr_(other.ptr_) { other.ptr_ = nullptr; }
        Ptr& operator=(Ptr&& other) noexcept {
            if (this != &other) { reset(); ptr_ = other.ptr_; other.ptr_ = nullptr; }
            return *this;
        }
        T* get() const noexcept { return ptr_; }
        void reset(T* p = nullptr) {
            if (ptr_) { free_str(ptr_); ptr_ = nullptr; }
            ptr_ = p;
        }
    private:
        static void free_str(char* p) { neon3_free_string(p); }
        T* ptr_ = nullptr;
    };
}

// Opaque C client handle (RAII).
class Client {
public:
    Client(const std::string& endpoint, bool allow_non_loopback = false,
           uint64_t timeout_ms = 5000) {
        char* error = nullptr;
        int rc = neon3_client_new(endpoint.c_str(), allow_non_loopback ? 1 : 0,
                                  timeout_ms, &handle_, &error);
        detail::check(rc, error);
    }
    ~Client() { if (handle_) { neon3_client_free(handle_); handle_ = nullptr; } }
    Client(const Client&) = delete;
    Client& operator=(const Client&) = delete;
    Client(Client&& other) noexcept : handle_(other.handle_) { other.handle_ = nullptr; }
    Client& operator=(Client&& other) noexcept {
        if (this != &other) {
            if (handle_) neon3_client_free(handle_);
            handle_ = other.handle_;
            other.handle_ = nullptr;
        }
        return *this;
    }

    bool health(const std::string& target = "wgpu-runtime") {
        char* error = nullptr;
        int healthy = 0;
        int rc = neon3_client_health(handle_, target.c_str(), &healthy, &error);
        detail::check(rc, error);
        return healthy == 1;
    }

    // Generic RPC returning the result JSON.
    std::string call(const std::string& target, const std::string& method,
                     const std::string& params_json = "{}") {
        char* error = nullptr;
        char* result = nullptr;
        int rc = neon3_client_call(handle_, target.c_str(), method.c_str(),
                                   params_json.c_str(), &result, &error);
        if (rc != NEON3_OK) {
            std::string message = error ? error : "neon3 rpc error";
            if (error) neon3_free_string(error);
            throw Error(rc, message);
        }
        detail::Ptr<char> owned(result);
        return std::string(owned.get() ? owned.get() : "");
    }

    // Mount a NUI Flow; returns surface_id (and revision in program).
    std::string mountFlow(const std::string& source) {
        char* error = nullptr;
        char* program = nullptr;
        int rc = neon3_ui_mount_flow(handle_, source.c_str(), &program, &error);
        detail::check(rc, error);
        detail::Ptr<char> owned(program);
        return std::string(owned.get() ? owned.get() : "");
    }

    // Open a shared surface; returns its generation.
    int64_t openSurface(const std::string& surface_id, uint32_t width,
                        uint32_t height, uint32_t buffer_count = 2) {
        char* error = nullptr;
        int64_t generation = -1;
        int rc = neon3_surface_open(handle_, surface_id.c_str(), width, height,
                                    buffer_count, &generation, &error);
        detail::check(rc, error);
        return generation;
    }

    // Save the latest completed frame of a shared surface to a PNG file.
    void savePng(const std::string& surface_id, const std::string& path) {
        char* error = nullptr;
        int rc = neon3_surface_save_png(handle_, surface_id.c_str(), path.c_str(), &error);
        detail::check(rc, error);
    }

    void shutdown() {
        char* error = nullptr;
        int rc = neon3_client_shutdown(handle_, &error);
        detail::check(rc, error);
    }

    /**
     * Upload 10 rows of vec4 to the shader's `view.extras[0..9]` uniform
     * (wgpu.ui.set_view_extras, v0.2.7).
     */
    void setViewExtras(const float (&extras)[10][4]) {
        char* error = nullptr;
        int rc = neon3_view_set_extras(handle_, extras, &error);
        detail::check(rc, error);
    }

    /// Pause a renderer-owned animation timeline (v0.2.10).
    void animationPause(const std::string& nodePath) {
        char* error = nullptr;
        int rc = neon3_animation_pause(handle_, nodePath.c_str(), &error);
        detail::check(rc, error);
    }

    /// Resume a paused animation timeline.
    void animationResume(const std::string& nodePath) {
        char* error = nullptr;
        int rc = neon3_animation_resume(handle_, nodePath.c_str(), &error);
        detail::check(rc, error);
    }

    /// Cancel an animation timeline.
    void animationCancel(const std::string& nodePath) {
        char* error = nullptr;
        int rc = neon3_animation_cancel(handle_, nodePath.c_str(), &error);
        detail::check(rc, error);
    }

    /// Seek an animation timeline to `progress` in [0, 1].
    void animationSeek(const std::string& nodePath, float progress) {
        char* error = nullptr;
        int rc = neon3_animation_seek(handle_, nodePath.c_str(), progress, &error);
        detail::check(rc, error);
    }

    void* nativeHandle() const noexcept { return handle_; }

private:
    neon3_client* handle_ = nullptr;
};

/**
 * Headless editor document client (editor-runtime, v0.2.10+).
 *
 * Wraps the `neon3_editor_*` C ABI: open documents, apply change sets
 * (draft/commit), request completions, and close. The C ABI returns raw JSON
 * for each call; this class keeps that shape so every language SDK exposes
 * the same wire contract. `EditorClient` borrows the `Client`'s handle —
 * keep the `Client` alive for the `EditorClient`'s lifetime.
 */
class EditorClient {
public:
    explicit EditorClient(Client& client) noexcept : handle_(client.nativeHandle()) {}

    /// editor.document.open — returns {"state": "opened"|"already_open", ...}.
    /// language must be "nui_flow".
    std::string open(const std::string& document_id, const std::string& session_id,
                     const std::string& source, const std::string& language) {
        char* error = nullptr;
        char* result = nullptr;
        int rc = neon3_editor_open(handle_, document_id.c_str(), session_id.c_str(),
                                   source.c_str(), language.c_str(), &result, &error);
        return finish(rc, result, error);
    }

    /// editor.document.snapshot.get — returns {"state": "ready", "snapshot": ...}.
    std::string snapshot(const std::string& document_id, const std::string& session_id,
                         uint64_t epoch) {
        char* error = nullptr;
        char* result = nullptr;
        int rc = neon3_editor_snapshot(handle_, document_id.c_str(), session_id.c_str(),
                                       epoch, &result, &error);
        return finish(rc, result, error);
    }

    /// editor.document.change.apply — `changeset_json` is
    /// {"base_revision": u64, "ops": [...]} with ops tagged kind insert/delete;
    /// `kind` is "draft" or "commit".
    std::string applyChange(const std::string& document_id, const std::string& session_id,
                            uint64_t epoch, const std::string& changeset_json,
                            const std::string& kind) {
        char* error = nullptr;
        char* result = nullptr;
        int rc = neon3_editor_apply(handle_, document_id.c_str(), session_id.c_str(),
                                    epoch, changeset_json.c_str(), kind.c_str(),
                                    &result, &error);
        return finish(rc, result, error);
    }

    /// editor.document.change.commit — envelope carries expected_revision;
    /// a stale value is rejected with editor_revision_conflict.
    std::string commit(const std::string& document_id, const std::string& session_id,
                       uint64_t epoch, uint64_t expected_revision) {
        char* error = nullptr;
        char* result = nullptr;
        int rc = neon3_editor_commit(handle_, document_id.c_str(), session_id.c_str(),
                                     epoch, expected_revision, &result, &error);
        return finish(rc, result, error);
    }

    /// editor.completion.request — trigger_kind is "automatic", "invoked",
    /// or "trigger_character".
    std::string completions(const std::string& document_id, const std::string& session_id,
                            uint64_t epoch, uint64_t document_revision,
                            uint32_t line, uint32_t column,
                            const std::string& trigger_kind) {
        char* error = nullptr;
        char* result = nullptr;
        int rc = neon3_editor_completions(handle_, document_id.c_str(), session_id.c_str(),
                                          epoch, document_revision, line, column,
                                          trigger_kind.c_str(), &result, &error);
        return finish(rc, result, error);
    }

    /// editor.document.close — returns {"state": "closed", ...}.
    std::string close(const std::string& document_id, const std::string& session_id,
                      uint64_t epoch) {
        char* error = nullptr;
        char* result = nullptr;
        int rc = neon3_editor_close(handle_, document_id.c_str(), session_id.c_str(),
                                    epoch, &result, &error);
        return finish(rc, result, error);
    }

private:
    static std::string finish(int rc, char* result, char* error) {
        if (rc != NEON3_OK) {
            std::string message = error ? error : "neon3 editor rpc error";
            if (error) neon3_free_string(error);
            throw Error(rc, message);
        }
        detail::Ptr<char> owned(result);
        return std::string(owned.get() ? owned.get() : "");
    }

    neon3_client* handle_;
};

/**
 * Long-lived eventd subscription (v0.2.7+, for shader.event and other bus
 * events). RAII: subscribes on construction and frees the handle on
 * destruction. `recv` blocks until one delivery frame arrives or the timeout
 * expires (timeout surfaces as neon3::Error with code NEON3_ERR_RPC).
 */
class EventSubscription {
public:
    EventSubscription(const std::string& endpoint, const std::string& name) {
        char* error = nullptr;
        int rc = neon3_event_subscribe(endpoint.c_str(), name.c_str(), &sub_, &error);
        detail::check(rc, error);
    }
    ~EventSubscription() {
        if (sub_) {
            neon3_event_subscription_free(sub_);
            sub_ = nullptr;
        }
    }
    EventSubscription(const EventSubscription&) = delete;
    EventSubscription& operator=(const EventSubscription&) = delete;
    EventSubscription(EventSubscription&& other) noexcept : sub_(other.sub_) {
        other.sub_ = nullptr;
    }
    EventSubscription& operator=(EventSubscription&& other) noexcept {
        if (this != &other) {
            if (sub_) neon3_event_subscription_free(sub_);
            sub_ = other.sub_;
            other.sub_ = nullptr;
        }
        return *this;
    }

    /// Block until one event envelope arrives; returns the event JSON
    /// ({event_id, payload, ...} or the raw envelope).
    std::string recv(uint64_t timeout_ms = 5000) {
        char* error = nullptr;
        char* event = nullptr;
        int rc = neon3_event_recv(sub_, timeout_ms, &event, &error);
        if (rc != NEON3_OK) {
            std::string message = error ? error : "neon3 event recv error";
            if (error) neon3_free_string(error);
            throw Error(rc, message);
        }
        detail::Ptr<char> owned(event);
        return std::string(owned.get() ? owned.get() : "");
    }

    neon3_event_subscription* nativeHandle() const noexcept { return sub_; }

private:
    neon3_event_subscription* sub_ = nullptr;
};

} // namespace neon3

#endif // NEON3_CPP_SDK_HPP
