#include "edgeai/MixedMatrix.hpp"
#include "edgeai/Binary.hpp"
#include <cmath>
#include <istream>
#include <ostream>
#include <type_traits>
namespace edgeai { namespace {
template<class T> void write(std::ostream& o,T v){o.write(reinterpret_cast<const char*>(&v),sizeof(v));if(!o)throw std::runtime_error("matrix write failed");}
template<class T> T read(std::istream& i){T v{};i.read(reinterpret_cast<char*>(&v),sizeof(v));if(!i)throw std::runtime_error("truncated mixed matrix");return v;}
bool valid_scale(float x){return std::isfinite(x)&&x>0&&std::isfinite(x*127.f);}
}
const char* precision_name(Precision p){switch(p){case Precision::Fp32:return "fp32";case Precision::Int8:return "int8_w8a32";case Precision::Ternary:return "ternary_2bit";}throw std::invalid_argument("unknown precision");}
Int8Matrix::Int8Matrix(std::size_t r,std::size_t c):rows_(r),cols_(c),weights_(binary::count(r,c),0),scales_(r,1),bias_(r,0){}
void Int8Matrix::set(std::size_t r,std::size_t c,int v){if(r>=rows_||c>=cols_)throw std::out_of_range("INT8 matrix index");if(v< -127||v>127)throw std::invalid_argument("INT8 code outside [-127,127]");weights_[r*cols_+c]=static_cast<std::int8_t>(v);}
int Int8Matrix::get(std::size_t r,std::size_t c)const{if(r>=rows_||c>=cols_)throw std::out_of_range("INT8 matrix index");return weights_[r*cols_+c];}
void Int8Matrix::set_scale(std::size_t r,float v){if(!valid_scale(v))throw std::invalid_argument("invalid INT8 scale");scales_.at(r)=v;}
void Int8Matrix::set_bias(std::size_t r,float v){if(!std::isfinite(v))throw std::invalid_argument("invalid INT8 bias");bias_.at(r)=v;}
std::vector<float> Int8Matrix::matvec(const std::vector<float>&x)const{std::vector<float>y(rows_);matvec_into(x.data(),x.size(),y.data(),y.size());return y;}
void Int8Matrix::matvec_into(const float*x,std::size_t n,float*y,std::size_t out_n,Kernel k)const{
    if(n!=cols_||out_n<rows_||!x||!y||x==y)throw std::invalid_argument("INT8 shape/pointer mismatch");
    int8_kernel(weights_.data(),scales_.data(),bias_.data(),rows_,cols_,x,y,k);
}
void Int8Matrix::save(std::ostream&o)const{
    binary::little_endian();binary::count(rows_,cols_);
    write(o,std::uint32_t(rows_));write(o,std::uint32_t(cols_));write(o,std::uint64_t(weights_.size()));
    o.write(reinterpret_cast<const char*>(weights_.data()),static_cast<std::streamsize>(weights_.size()));
    o.write(reinterpret_cast<const char*>(scales_.data()),static_cast<std::streamsize>(rows_*4));
    o.write(reinterpret_cast<const char*>(bias_.data()),static_cast<std::streamsize>(rows_*4));
    if(!o)throw std::runtime_error("INT8 write failed");
}
Int8Matrix Int8Matrix::load(std::istream&i){
    binary::little_endian();auto r=read<std::uint32_t>(i),c=read<std::uint32_t>(i);auto n=read<std::uint64_t>(i);
    auto count=binary::count(r,c);if(n!=count)throw std::runtime_error("invalid INT8 payload size");
    binary::remaining(i,count+std::size_t(r)*8);Int8Matrix m(r,c);
    i.read(reinterpret_cast<char*>(m.weights_.data()),static_cast<std::streamsize>(count));
    i.read(reinterpret_cast<char*>(m.scales_.data()),static_cast<std::streamsize>(r)*4);
    i.read(reinterpret_cast<char*>(m.bias_.data()),static_cast<std::streamsize>(r)*4);
    if(!i)throw std::runtime_error("truncated INT8 matrix");
    for(auto v:m.weights_)if(v== -128)throw std::runtime_error("reserved INT8 code");
    for(float v:m.scales_)if(!valid_scale(v))throw std::runtime_error("invalid INT8 row scale");
    if(!binary::finite(m.bias_.data(),r))throw std::runtime_error("nonfinite INT8 bias");
    return m;
}
Precision MixedMatrix::kind()const{
    if(std::holds_alternative<DenseMatrix>(matrix_))return Precision::Fp32;
    if(std::holds_alternative<Int8Matrix>(matrix_))return Precision::Int8;
    return Precision::Ternary;
}
std::size_t MixedMatrix::rows()const{return std::visit([](const auto&m){return m.rows();},matrix_);}
std::size_t MixedMatrix::cols()const{return std::visit([](const auto&m){return m.cols();},matrix_);}
std::size_t MixedMatrix::storage_bytes()const{return std::visit([](const auto&m){return m.storage_bytes();},matrix_);}
std::vector<float> MixedMatrix::matvec(const std::vector<float>&x)const{std::vector<float>y(rows());matvec_into(x.data(),x.size(),y.data(),y.size());return y;}
void MixedMatrix::matvec_into(const float*x,std::size_t n,float*y,std::size_t out_n,Kernel k,KernelWorkspace*w)const{
    std::visit([&](const auto&m){using M=std::decay_t<decltype(m)>;
        if constexpr(std::is_same_v<M,TernaryMatrix>)m.matvec_into(x,n,y,out_n,k,w);
        else m.matvec_into(x,n,y,out_n,k);
    },matrix_);
}
void MixedMatrix::save(std::ostream&o)const{write(o,std::uint32_t(kind()));std::visit([&](const auto&m){m.save(o);},matrix_);}
MixedMatrix MixedMatrix::load(std::istream&i){
    auto code=read<std::uint32_t>(i);
    switch(code){case 0:return DenseMatrix::load(i);case 1:return Int8Matrix::load(i);case 2:return TernaryMatrix::load(i);default:throw std::runtime_error("unknown matrix dtype tag");}
}
}
