#include "edgeai/CodeSearch.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
namespace {
// Consume an oversized line without retaining unbounded input in memory.
bool read_query(std::istream&in,std::string&q){q.clear();char c;bool any=false,overflow=false;while(in.get(c)){any=true;if(c=='\n')break;if(q.size()<513)q+=c;else overflow=true;}if(!overflow&&!q.empty()&&q.back()=='\r')q.pop_back();return any;}
}
int main(int argc,char**argv){try{
 if(argc<3){std::cerr<<"edgeai_code_search ROOT QUERY|--batch [--json] [--limit 1..20] [--context 0..10]\n";return 2;}
 bool json=false,batch=std::string(argv[2])=="--batch";std::size_t limit=5,context=2;
 for(int i=3;i<argc;++i){std::string a=argv[i];if(a=="--json"){json=true;continue;}
  if((a!="--limit"&&a!="--context")||i+1>=argc)throw std::invalid_argument("invalid argument: "+a);
  std::string v=argv[++i];if(v.empty()||v.find_first_not_of("0123456789")!=std::string::npos)throw std::invalid_argument("integer required");
  auto n=std::stoul(v);if(a=="--limit")limit=n;else context=n;
 }
 if(limit<1||limit>20||context>10)throw std::invalid_argument("limit 1..20 and context 0..10 required");
 edgeai::CodeIndex idx(argv[1]);bool failed=false;
 auto answer=[&](const std::string&q,bool refresh){try{if(refresh)idx.refresh();auto r=idx.search(q,limit,context);std::cout<<(json?edgeai::code_result_json(r):edgeai::format_code_result(r))<<std::endl;}
 catch(const std::exception&e){failed=true;std::cerr<<"Erro: "<<e.what()<<'\n';if(json)std::cout<<"{\"error\":\"query_or_refresh_failed\",\"hits\":[],\"neural_used\":false}"<<std::endl;else std::cout<<"Falha na consulta; nenhum resultado anterior foi reutilizado.\n"<<std::flush;}};
 if(batch){std::string q;while(read_query(std::cin,q)){answer(q,true);}}
 else answer(argv[2],false);
 return failed?1:0;
 }catch(const std::exception&e){std::cerr<<"Erro: "<<e.what()<<'\n';return 1;}}
