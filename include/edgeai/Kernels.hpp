#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>
namespace edgeai {
enum class Kernel { Auto, Scalar, Lookup, Avx2 };
struct KernelWorkspace { std::vector<float> pairs; std::size_t bytes() const { return pairs.capacity()*sizeof(float); } };
bool avx2_available();
const char* kernel_name(Kernel kernel);
Kernel select_kernel(std::size_t rows, std::size_t cols, Kernel requested=Kernel::Auto);
void ternary_kernel(const std::uint8_t* packed, const float* scales, const float* bias,
                    std::size_t rows, std::size_t cols, const float* x, float* y,
                    Kernel requested, KernelWorkspace* workspace=nullptr);
void dense_kernel(const float* weights, const float* bias, std::size_t rows,
                  std::size_t cols, const float* x, float* y, Kernel requested);
void int8_kernel(const std::int8_t* weights,const float* scales,const float* bias,
                 std::size_t rows,std::size_t cols,const float* x,float* y,Kernel requested);
}
