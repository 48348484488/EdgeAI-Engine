#include "edgeai/Ternary.hpp"
#include "edgeai/Binary.hpp"
#include <cmath>
#include <algorithm>
#include <array>
#include <cstring>
#include <istream>
#include <ostream>
#include <stdexcept>

namespace edgeai {
namespace {
template <class T> void write_pod(std::ostream& out, const T& v) {
    out.write(reinterpret_cast<const char*>(&v), sizeof(T));
    if (!out) throw std::runtime_error("failed writing matrix");
}
template <class T> T read_pod(std::istream& in) {
    T v{}; in.read(reinterpret_cast<char*>(&v), sizeof(T));
    if (!in) throw std::runtime_error("failed reading matrix");
    return v;
}
void write_vec(std::ostream& out, const void* p, std::size_t bytes) {
    if (bytes) out.write(reinterpret_cast<const char*>(p), static_cast<std::streamsize>(bytes));
    if (!out) throw std::runtime_error("failed writing matrix data");
}
void read_vec(std::istream& in, void* p, std::size_t bytes) {
    if (bytes) in.read(reinterpret_cast<char*>(p), static_cast<std::streamsize>(bytes));
    if (!in) throw std::runtime_error("failed reading matrix data");
}
inline std::uint8_t code_for(int v) { return v > 0 ? 1u : (v < 0 ? 2u : 0u); }
inline int value_for(std::uint8_t code) { return code == 1u ? 1 : (code == 2u ? -1 : 0); }
}

TernaryMatrix::TernaryMatrix(std::size_t rows, std::size_t cols)
    : rows_(rows), cols_(cols), packed_((binary::count(rows,cols) + 3) / 4, 0), scales_(rows, 1.0f), bias_(rows, 0.0f) {}

std::size_t TernaryMatrix::storage_bytes() const { return packed_.size() + (scales_.size() + bias_.size()) * sizeof(float); }

void TernaryMatrix::set(std::size_t r, std::size_t c, int value) {
    if (r >= rows_ || c >= cols_) throw std::out_of_range("ternary index");
    if(value < -1 || value > 1) throw std::invalid_argument("invalid ternary weight");
    const std::size_t idx = r * cols_ + c, b = idx >> 2, shift = (idx & 3u) * 2u;
    packed_[b] = static_cast<std::uint8_t>((packed_[b] & ~(std::uint8_t(3u) << shift)) | (code_for(value) << shift));
}
int TernaryMatrix::get(std::size_t r, std::size_t c) const {
    if (r >= rows_ || c >= cols_) throw std::out_of_range("ternary index");
    const std::size_t idx = r * cols_ + c, b = idx >> 2, shift = (idx & 3u) * 2u;
    return value_for(static_cast<std::uint8_t>((packed_[b] >> shift) & 3u));
}
void TernaryMatrix::set_scale(std::size_t r, float value) { if(!std::isfinite(value)||value<0) throw std::invalid_argument("invalid scale"); scales_.at(r) = value; }
void TernaryMatrix::set_bias(std::size_t r, float value) { if(!std::isfinite(value)) throw std::invalid_argument("invalid bias"); bias_.at(r) = value; }

std::vector<float> TernaryMatrix::matvec(const std::vector<float>& x) const {
    std::vector<float> out(rows_); matvec_into(x.data(), x.size(), out.data(), out.size()); return out;
}
void TernaryMatrix::matvec_into(const float* x, std::size_t n, float* out, std::size_t out_n, Kernel kernel, KernelWorkspace* workspace) const {
    if(n!=cols_||out_n<rows_||!x||!out||x==out)throw std::runtime_error("ternary matvec shape/pointer mismatch");
    ternary_kernel(packed_.data(),scales_.data(),bias_.data(),rows_,cols_,x,out,kernel,workspace);
}

void TernaryMatrix::save(std::ostream& out) const {
    const std::uint32_t r = static_cast<std::uint32_t>(rows_), c = static_cast<std::uint32_t>(cols_);
    write_pod(out, r); write_pod(out, c);
    const std::uint64_t pb = static_cast<std::uint64_t>(packed_.size()); write_pod(out, pb);
    write_vec(out, packed_.data(), packed_.size());
    write_vec(out, scales_.data(), scales_.size() * sizeof(float));
    write_vec(out, bias_.data(), bias_.size() * sizeof(float));
}
TernaryMatrix TernaryMatrix::load(std::istream& in) {
    const auto r = read_pod<std::uint32_t>(in), c = read_pod<std::uint32_t>(in);
    const auto pb = read_pod<std::uint64_t>(in);
    const auto elements=binary::count(r,c); binary::little_endian();
    if(pb!=(elements+3)/4)throw std::runtime_error("invalid packed length");
    binary::remaining(in,static_cast<std::size_t>(pb)+std::size_t(r)*8);
    TernaryMatrix m(r, c);
    if (pb != m.packed_.size()) throw std::runtime_error("invalid ternary packed size");
    read_vec(in, m.packed_.data(), m.packed_.size());
    read_vec(in, m.scales_.data(), m.scales_.size() * sizeof(float));
    read_vec(in, m.bias_.data(), m.bias_.size() * sizeof(float));
    if(!binary::finite(m.scales_.data(),r)||!binary::finite(m.bias_.data(),r))throw std::runtime_error("nonfinite matrix values");
    for(float v:m.scales_)if(v<0)throw std::runtime_error("negative scale");
    for(std::size_t k=0;k<elements;++k)if(((m.packed_[k/4]>>((k%4)*2))&3u)==3)throw std::runtime_error("reserved ternary code");
    return m;
}

DenseMatrix::DenseMatrix(std::size_t r, std::size_t c): rows_(r), cols_(c), weights_(binary::count(r,c),0.0f), bias_(r,0.0f) {}
std::size_t DenseMatrix::storage_bytes() const { return (weights_.size()+bias_.size())*sizeof(float); }
std::vector<float> DenseMatrix::matvec(const std::vector<float>& x) const { std::vector<float> y(rows_); matvec_into(x.data(),x.size(),y.data(),y.size()); return y; }
void DenseMatrix::matvec_into(const float* x,std::size_t n,float* out,std::size_t out_n,Kernel kernel) const {
    if(n!=cols_||out_n<rows_||!x||!out||x==out)throw std::runtime_error("dense matvec shape/pointer mismatch");
    dense_kernel(weights_.data(),bias_.data(),rows_,cols_,x,out,kernel);
}

void DenseMatrix::save(std::ostream& out) const { const std::uint32_t r=static_cast<std::uint32_t>(rows_),c=static_cast<std::uint32_t>(cols_); write_pod(out,r);write_pod(out,c);write_vec(out,weights_.data(),weights_.size()*sizeof(float));write_vec(out,bias_.data(),bias_.size()*sizeof(float)); }
DenseMatrix DenseMatrix::load(std::istream& in){
    binary::little_endian();const auto r=read_pod<std::uint32_t>(in),c=read_pod<std::uint32_t>(in);
    auto count=binary::count(r,c);binary::remaining(in,(count+r)*sizeof(float));
    DenseMatrix m(r,c);read_vec(in,m.weights_.data(),m.weights_.size()*sizeof(float));read_vec(in,m.bias_.data(),m.bias_.size()*sizeof(float));
    if(!binary::finite(m.weights_.data(),m.weights_.size())||!binary::finite(m.bias_.data(),r))throw std::runtime_error("nonfinite dense matrix");
    return m;
}

} // namespace edgeai
