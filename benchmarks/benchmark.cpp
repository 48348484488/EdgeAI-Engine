#include "edgeai/Engine.hpp"
#include <chrono>
#include <iostream>
#include <memory>
int main(){
    edgeai::Engine e(edgeai::Mode::Eco,":memory:",std::make_shared<edgeai::EchoReasonerBackend>());
    constexpr int N=200000;
    volatile std::size_t sink=0;
    auto t0=std::chrono::steady_clock::now();
    for(int i=0;i<N;++i){ auto r=e.ask("253 * 719 + 4"); sink += r.text.size(); }
    auto t1=std::chrono::steady_clock::now();
    double s=std::chrono::duration<double>(t1-t0).count();
    std::cout<<"operations="<<N<<" seconds="<<s<<" ops_per_sec="<<(N/s)<<" sink="<<sink<<"\n";
}
