#pragma once
#include "Kernels.hpp"
#include <cstddef>
#include <cstdint>
#include <iosfwd>
#include <string>
#include <vector>

namespace edgeai {

// A compact row-major matrix with four ternary {-1,0,+1} weights packed per byte.
// Codes: 0 => 0, 1 => +1, 2 => -1, 3 => rejected on load.
class TernaryMatrix {
public:
    TernaryMatrix() = default;
    TernaryMatrix(std::size_t rows, std::size_t cols);

    std::size_t rows() const { return rows_; }
    std::size_t cols() const { return cols_; }
    std::size_t weight_count() const { return rows_ * cols_; }
    std::size_t packed_bytes() const { return packed_.size(); }
    std::size_t storage_bytes() const;

    void set(std::size_t row, std::size_t col, int value);
    int get(std::size_t row, std::size_t col) const;
    void set_scale(std::size_t row, float value);
    void set_bias(std::size_t row, float value);
    float scale(std::size_t row) const { return scales_.at(row); }
    float bias(std::size_t row) const { return bias_.at(row); }

    std::vector<float> matvec(const std::vector<float>& x) const;
    void matvec_into(const float* x, std::size_t n, float* out, std::size_t out_n, Kernel kernel=Kernel::Auto, KernelWorkspace* workspace=nullptr) const;

    void save(std::ostream& out) const;
    static TernaryMatrix load(std::istream& in);

private:
    std::size_t rows_ = 0;
    std::size_t cols_ = 0;
    std::vector<std::uint8_t> packed_;
    std::vector<float> scales_;
    std::vector<float> bias_;
};

class DenseMatrix {
public:
    DenseMatrix() = default;
    DenseMatrix(std::size_t rows, std::size_t cols);
    std::size_t rows() const { return rows_; }
    std::size_t cols() const { return cols_; }
    std::size_t storage_bytes() const;
    float& weight(std::size_t r, std::size_t c) { return weights_.at(r * cols_ + c); }
    float weight(std::size_t r, std::size_t c) const { return weights_.at(r * cols_ + c); }
    float& bias(std::size_t r) { return bias_.at(r); }
    float bias(std::size_t r) const { return bias_.at(r); }
    std::vector<float> matvec(const std::vector<float>& x) const;
    void matvec_into(const float* x, std::size_t n, float* out, std::size_t out_n, Kernel kernel=Kernel::Auto) const;
    void save(std::ostream& out) const;
    static DenseMatrix load(std::istream& in);
private:
    std::size_t rows_ = 0, cols_ = 0;
    std::vector<float> weights_, bias_;
};

} // namespace edgeai
