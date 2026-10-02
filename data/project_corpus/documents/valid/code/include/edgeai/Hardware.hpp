#pragma once
#include <string>
namespace edgeai {
struct HardwareInfo { unsigned threads; bool sse2; bool avx; bool avx2; std::string summary() const; };
HardwareInfo detect_hardware();
}
