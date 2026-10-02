#include "edgeai/HybridBackend.hpp"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <stdexcept>
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(false)
int main(){using namespace edgeai;auto model=make_hybrid_demo(16,8,4);CHECK(model.valid());model.save("hybrid-test.edge");auto m=HybridModel::load("hybrid-test.edge");CHECK(m.weight_bytes()==model.weight_bytes());HybridBackend b(m,Kernel::Scalar);auto first=b.step(22);for(int i=0;i<80;++i)b.step(i%256);CHECK(b.tokens_seen()==81);auto bytes=b.numeric_working_bytes();for(int i=0;i<100;++i)b.step(i%256);CHECK(b.numeric_working_bytes()==bytes);b.reset();CHECK(b.tokens_seen()==0);auto again=b.step(22);for(std::size_t i=0;i<first.size();++i)CHECK(std::abs(first[i]-again[i])<1e-6);
 auto loaded=load_backend("hybrid-test.edge");CHECK(loaded->available());Budget budget{2,256,1,1};auto x=loaded->infer("ola",budget),y=loaded->infer("ola",budget);CHECK(x.text==y.text);
 std::ofstream append("hybrid-test.edge",std::ios::binary|std::ios::app);append.put('X');append.close();bool caught=false;try{HybridModel::load("hybrid-test.edge");}catch(const std::exception&){caught=true;}CHECK(caught);std::remove("hybrid-test.edge");
 std::cout<<"hybrid load/reset/state-bound checks passed\n";}
