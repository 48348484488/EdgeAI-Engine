#include "edgeai/EdgeModel.hpp"
#include <iostream>
int main(int argc,char**argv){try{std::string p=argc>1?argv[1]:"models/demo.edge";auto m=edgeai::make_demo_edge_model();m.save(p);std::cout<<"saved "<<p<<" params="<<m.parameter_count()<<" resident_bytes="<<m.resident_weight_bytes()<<" fp32_equiv="<<m.fp32_equivalent_bytes()<<" compression="<<m.compression_ratio_vs_fp32()<<"x\n";}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
