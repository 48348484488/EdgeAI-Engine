// Original v0.9 search, with a line-oriented wrapper for equal process lifetimes.
#include "edgeai/CodeSearch.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
int main(int argc,char**argv){try{
 if(argc<3)throw std::invalid_argument("ROOT QUERY|--batch [--json]");
 if(std::string(argv[2])=="--batch"){
  std::string q;while(std::getline(std::cin,q)){
   if(!q.empty()&&q.back()=='\r')q.pop_back();
   auto r=edgeai::CodeIndex(argv[1]).search(q);
   std::cout<<edgeai::code_result_json(r)<<std::endl;
  }
 }else std::cout<<edgeai::code_result_json(edgeai::CodeIndex(argv[1]).search(argv[2]))<<'\n';
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
