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

    void* nativeHandle() const noexcept { return handle_; }

private:
    neon3_client* handle_ = nullptr;
};

} // namespace neon3

#endif // NEON3_CPP_SDK_HPP
