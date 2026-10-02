#pragma once
#include "Types.hpp"
#include <string>
namespace edgeai {
class Scheduler {
public:
    explicit Scheduler(Mode mode = Mode::Balanced) : mode_(mode) {}
    void set_mode(Mode mode) { mode_ = mode; }
    Mode mode() const { return mode_; }
    Budget budget_for(const std::string& prompt) const;
private:
    Mode mode_;
};
}
