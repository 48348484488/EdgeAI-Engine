#include "edgeai/Scheduler.hpp"
namespace edgeai {
Budget Scheduler::budget_for(const std::string&) const {
    // Bounds, not calibrated difficulty estimates. Neural kernels currently use one thread.
    // Models retain their trained depth; a model exceeding a bound is rejected, not silently changed.
    if (mode_ == Mode::Eco) return {2, 2048, 3, 1};
    if (mode_ == Mode::Max) return {8, 16384, 8, 1};
    return {4, 8192, 5, 1};
}
}
