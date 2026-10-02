#include "edgeai/Hardware.hpp"
#include <sstream>
#include <algorithm>
#include <thread>
namespace edgeai {
HardwareInfo detect_hardware(){
    HardwareInfo h{}; h.threads=std::max(1u,std::thread::hardware_concurrency());
#if defined(__x86_64__) || defined(_M_X64) || defined(__i386) || defined(_M_IX86)
    h.sse2=true;
#else
    h.sse2=false;
#endif
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
    __builtin_cpu_init();h.sse2=bool(__builtin_cpu_supports("sse2"));h.avx=bool(__builtin_cpu_supports("avx"));h.avx2=bool(__builtin_cpu_supports("avx2"));
#else
    h.avx=false;h.avx2=false;
#endif
    return h;
}
std::string HardwareInfo::summary() const{ std::ostringstream o; o<<"threads="<<threads<<" sse2="<<sse2<<" avx="<<avx<<" avx2="<<avx2; return o.str(); }
}
