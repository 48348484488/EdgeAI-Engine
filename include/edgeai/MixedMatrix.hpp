#pragma once
#include "Ternary.hpp"
#include <variant>
#include <utility>
namespace edgeai {
enum class Precision : std::uint32_t { Fp32=0, Int8=1, Ternary=2 };
const char* precision_name(Precision p);
// Symmetric per-row INT8 weights. Activations, accumulation and bias are FP32.
class Int8Matrix {
public:
    Int8Matrix()=default;
    Int8Matrix(std::size_t rows,std::size_t cols);
    std::size_t rows()const{return rows_;}
    std::size_t cols()const{return cols_;}
    std::size_t storage_bytes()const{return weights_.size()+8*rows_;}
    void set(std::size_t r,std::size_t c,int value);
    int get(std::size_t r,std::size_t c)const;
    void set_scale(std::size_t r,float scale);
    void set_bias(std::size_t r,float bias);
    float scale(std::size_t r)const{return scales_.at(r);}
    float bias(std::size_t r)const{return bias_.at(r);}
    std::vector<float> matvec(const std::vector<float>& x)const;
    void matvec_into(const float* x,std::size_t n,float* y,std::size_t out_n,Kernel kernel=Kernel::Auto)const;
    void save(std::ostream& out)const;
    static Int8Matrix load(std::istream& in);
private:
    std::size_t rows_=0,cols_=0;
    std::vector<std::int8_t> weights_;
    std::vector<float> scales_,bias_;
};
// No dense copy/cache is retained alongside a quantized matrix.
class MixedMatrix {
public:
    MixedMatrix()=default;
    MixedMatrix(TernaryMatrix m):matrix_(std::move(m)){}
    MixedMatrix(DenseMatrix m):matrix_(std::move(m)){}
    MixedMatrix(Int8Matrix m):matrix_(std::move(m)){}
    Precision kind()const;
    std::size_t rows()const;
    std::size_t cols()const;
    std::size_t weight_count()const{return rows()*cols();}
    std::size_t storage_bytes()const;
    std::vector<float> matvec(const std::vector<float>& x)const;
    void matvec_into(const float* x,std::size_t n,float* y,std::size_t out_n,Kernel kernel=Kernel::Auto,KernelWorkspace* workspace=nullptr)const;
    void save(std::ostream& out)const;
    static MixedMatrix load(std::istream& in);
private:
    std::variant<TernaryMatrix,DenseMatrix,Int8Matrix> matrix_;
};
}
