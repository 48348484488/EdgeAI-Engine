#include "edgeai/HybridMemory.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace edgeai;
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(false)
int main(){
 DeltaMemory m(4,2);std::vector<float>k{1,0,0,0},q{0,1,0,0},v{2,3},w{8,9},out(2);
 m.update(k,v,1,1);m.read(k,out);CHECK(std::abs(out[0]-2)<1e-6);m.update(q,w,1,1);m.read(k,out);CHECK(std::abs(out[1]-3)<1e-6);
 m.update(k,w,1,1);m.read(k,out);CHECK(std::abs(out[0]-8)<1e-6);m.read(q,out);CHECK(std::abs(out[1]-9)<1e-6);
 auto bytes=m.storage_bytes();for(int i=0;i<1000;++i)m.update(k,v,1,1);CHECK(m.storage_bytes()==bytes);m.reset();m.read(k,out);CHECK(out[0]==0);
 LocalAttention a(4,2,2);a.push(k,v);a.read(k,out);CHECK(std::abs(out[0]-2)<1e-6);a.push(q,w);a.push(q,w);CHECK(a.size()==2);a.read(k,out);CHECK(std::abs(out[0]-8)<1e-6);a.reset();a.read(k,out);CHECK(out[0]==0);
 bool caught=false;try{m.update(std::vector<float>{1},v,1,1);}catch(const std::exception&){caught=true;}CHECK(caught);
 caught=false;try{m.update(k,v,1.1f,1);}catch(const std::exception&){caught=true;}CHECK(caught);
 std::cout<<"hybrid memory checks passed\n";
}
