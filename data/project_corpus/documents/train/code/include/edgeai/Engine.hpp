#pragma once
#include "Backend.hpp"
#include "Hardware.hpp"
#include "Memory.hpp"
#include "Scheduler.hpp"
#include "Types.hpp"
#include <string>
namespace edgeai {
class Engine {
public:
    explicit Engine(Mode mode = Mode::Balanced, std::string memory_path = "edgeai_memory.txt", BackendPtr backend = nullptr);
    Response ask(const std::string& text);
    void set_mode(Mode mode) { scheduler_.set_mode(mode); }
    void set_backend(BackendPtr backend);
    const HardwareInfo& hardware() const { return hardware_; }
    const IModelBackend& backend() const { return *backend_; }
    std::size_t memory_size() const { return memory_.size(); }
private:
    HardwareInfo hardware_;
    Scheduler scheduler_;
    LocalMemory memory_;
    BackendPtr backend_;
};
}
