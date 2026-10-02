#include "edgeai/Ternary.hpp"
#include <cmath>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
using namespace edgeai;
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(false)
int main(){std::mt19937 g(123);std::uniform_real_distribution<float>f(-2,2);std::uniform_int_distribution<int>q(-1,1);int cases=0;
 for(std::size_t r:{1,3,17,33})for(std::size_t c:{1,2,3,4,5,7,8,9,16,31,32,127,128,256}){
  TernaryMatrix t(r,c);DenseMatrix d(r,c);std::vector<float>x(c),ref(r),out(r);for(auto&v:x)v=f(g);
  for(std::size_t i=0;i<r;++i){float s=.01f+std::abs(f(g));t.set_scale(i,s);float b=f(g);t.set_bias(i,b);d.bias(i)=b;for(std::size_t j=0;j<c;++j){auto z=q(g);t.set(i,j,z);d.weight(i,j)=s*z;}}
  d.matvec_into(x.data(),c,ref.data(),r,Kernel::Scalar);
  for(auto k:{Kernel::Scalar,Kernel::Lookup,Kernel::Auto,Kernel::Avx2}){
   if(k==Kernel::Avx2&&!avx2_available())continue;t.matvec_into(x.data(),c,out.data(),r,k);for(std::size_t i=0;i<r;++i)CHECK(std::abs(ref[i]-out[i])<2e-4);++cases;}
  std::stringstream ss(std::ios::in|std::ios::out|std::ios::binary);t.save(ss);auto loaded=TernaryMatrix::load(ss);CHECK(loaded.packed_bytes()==t.packed_bytes());for(std::size_t i=0;i<r;++i)for(std::size_t j=0;j<c;++j)CHECK(loaded.get(i,j)==t.get(i,j));
 }
 bool caught=false;try{std::istringstream s(std::string(16,'\xff'));auto x=TernaryMatrix::load(s);(void)x;}catch(const std::exception&){caught=true;}CHECK(caught);
 std::cout<<cases<<" kernel shape/backend cases passed\n";
}
