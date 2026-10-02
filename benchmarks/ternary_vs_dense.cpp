#include "edgeai/Ternary.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <vector>
using namespace edgeai;
int main(int argc,char**argv){try{
 std::size_t n=argc>1?std::stoul(argv[1]):256,reps=argc>2?std::stoul(argv[2]):100,rounds=argc>3?std::stoul(argv[3]):7;
 if(n<1||n>4096||reps<1||reps>100000||rounds<1||rounds>99)throw std::invalid_argument("benchmark limits");
 DenseMatrix d(n,n);TernaryMatrix t(n,n);std::mt19937 rng(912);std::uniform_real_distribution<float> f(-1,1);std::uniform_int_distribution<int> q(-1,1);std::vector<float>x(n),y(n),ref(n);KernelWorkspace workspace;
 for(auto&v:x)v=f(rng);for(std::size_t r=0;r<n;++r){float scale=.08f,bias=f(rng);t.set_scale(r,scale);t.set_bias(r,bias);d.bias(r)=bias;for(std::size_t c=0;c<n;++c){int value=q(rng);t.set(r,c,value);d.weight(r,c)=value*scale;}}
 // Double-precision accumulation is an independent numerical reference.
 for(std::size_t r=0;r<n;++r){double sum=d.bias(r);for(std::size_t c=0;c<n;++c)sum+=double(d.weight(r,c))*x[c];ref[r]=float(sum);}
 struct Case{const char* name;bool ternary;Kernel kernel;std::vector<double> times;float err=0;double checksum=0;};
 std::vector<Case> cases={{"dense_scalar",false,Kernel::Scalar,{}},{"ternary_scalar",true,Kernel::Scalar,{}},{"ternary_lookup2",true,Kernel::Lookup,{}}};
 if(avx2_available()){cases.push_back({"dense_avx2",false,Kernel::Avx2,{}});cases.push_back({"ternary_avx2",true,Kernel::Avx2,{}});}
 auto run=[&](Case& c){if(c.ternary)t.matvec_into(x.data(),n,y.data(),n,c.kernel,&workspace);else d.matvec_into(x.data(),n,y.data(),n,c.kernel);};
 for(auto&c:cases){for(int k=0;k<30;++k)run(c);for(std::size_t j=0;j<n;++j)c.err=std::max(c.err,std::abs(y[j]-ref[j]));if(c.err>2e-3f)throw std::runtime_error("numerical validation failed");}
 std::vector<std::size_t> order(cases.size());std::iota(order.begin(),order.end(),0);
 for(std::size_t r=0;r<rounds;++r){std::shuffle(order.begin(),order.end(),rng);for(auto index:order){auto&c=cases[index];auto start=std::chrono::steady_clock::now();for(std::size_t k=0;k<reps;++k)run(c);double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();c.times.push_back(elapsed*1e6/reps);c.checksum+=std::accumulate(y.begin(),y.end(),0.0);}}
 std::cout<<std::setprecision(10)<<"{\"dimension\":"<<n<<",\"repetitions\":"<<reps<<",\"rounds\":"<<rounds<<",\"dense_weight_bytes\":"<<d.storage_bytes()<<",\"ternary_weight_bytes\":"<<t.storage_bytes()<<",\"lut_workspace_bytes\":"<<workspace.bytes()<<",\"threads\":1,\"energy_joules\":null,\"cases\":[";
 for(std::size_t j=0;j<cases.size();++j){auto&c=cases[j];auto times=c.times;std::sort(times.begin(),times.end());if(j)std::cout<<",";std::cout<<"{\"name\":\""<<c.name<<"\",\"median_us_per_matvec\":"<<times[times.size()/2]<<",\"min_us\":"<<times.front()<<",\"max_us\":"<<times.back()<<",\"max_abs_error\":"<<c.err<<",\"checksum\":"<<c.checksum<<",\"raw_us\":[";for(std::size_t k=0;k<c.times.size();++k){if(k)std::cout<<",";std::cout<<c.times[k];}std::cout<<"]}";}
 std::cout<<"]}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
