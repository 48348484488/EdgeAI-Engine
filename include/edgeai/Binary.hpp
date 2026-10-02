#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>
#include <istream>
#include <limits>
#include <stdexcept>
namespace edgeai { namespace binary {
inline void little_endian() { std::uint32_t x=1; if(*reinterpret_cast<unsigned char*>(&x)!=1)throw std::runtime_error(".edge currently requires little-endian hardware"); }
inline std::size_t count(std::size_t rows,std::size_t cols) {
    constexpr std::size_t max_elements=64u*1024u*1024u;
    if(!rows||!cols||rows>65536||cols>65536||rows>max_elements/cols)throw std::runtime_error("invalid or oversized tensor dimensions");
    return rows*cols;
}
inline void remaining(std::istream& in,std::size_t bytes) {
    auto pos=in.tellg();if(pos==std::streampos(-1))throw std::runtime_error("model stream must be seekable");
    in.seekg(0,std::ios::end);auto end=in.tellg();in.seekg(pos);
    if(!in||end<pos||static_cast<std::uint64_t>(end-pos)<bytes)throw std::runtime_error("truncated model payload");
}
inline bool finite(const float* v,std::size_t n){for(std::size_t i=0;i<n;++i)if(!std::isfinite(v[i]))return false;return true;}
} }
