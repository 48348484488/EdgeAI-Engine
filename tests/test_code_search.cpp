#include "edgeai/CodeSearch.hpp"
#include "edgeai/Engine.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#define CHECK(x) do { if(!(x)) throw std::runtime_error("CHECK failed: " #x); } while(false)
namespace fs=std::filesystem;
void put(const fs::path& p,const std::string& v){fs::create_directories(p.parent_path());std::ofstream o(p,std::ios::binary);o<<v;}
template<class F> void fails(F f){bool caught=false;try{f();}catch(const std::exception&){caught=true;}CHECK(caught);}
int main(){
 auto root=fs::temp_directory_path()/("edgeai-search-"+std::to_string(std::chrono::high_resolution_clock::now().time_since_epoch().count()));
 fs::create_directories(root);
 try {
  put(root/"src/player.cpp","// spawn logic\nvoid SpawnPlayer(int id) {\n    set_health(id, 100);\n}\n");
  put(root/"src/caller.cpp","void caller() { SpawnPlayer(1); }\n");
  put(root/"web/app.js","function renderMenu() {\n  return 'menu';\n}\n");
  put(root/"script/login.pwn","stock CarregarConta(playerid) {\n return 1;\n}\n");
  put(root/"unicode/ação.py", "def ola():\n    return 'ação 😊'\n");
  put(root/".env","SpawnPlayer=hidden\n");put(root/".git/index.cpp","secretToken();\n");
  put(root/"node_modules/dep.js","function dependencySecret() {}\n");
  put(root/"secret_keys.py","def secretToken(): pass\n");
  put(root/"nul.cpp",std::string("not\0source",10));
  put(root/"invalid.py",std::string("def x():\xff",9));
  std::error_code ec;fs::create_symlink(root/"src/player.cpp",root/"alias.cpp",ec);
  edgeai::CodeIndex idx(root.string());auto r=idx.search("Onde fica a função SpawnPlayer?",3,1);
  CHECK(r.hits.size()==2);CHECK(r.hits[0].path=="src/player.cpp");CHECK(r.hits[0].match_line==2);
  CHECK(r.hits[0].start_line==1&&r.hits[0].end_line==3);
  CHECK(r.hits[0].text=="// spawn logic\nvoid SpawnPlayer(int id) {\n    set_health(id, 100);");
  CHECK(!r.neural_used&&!r.partial);CHECK(r.scanned_files==5);CHECK(r.skipped_files>=3);
  CHECK(idx.search("`SpawnPlay`",3,0).hits.empty());
  CHECK(idx.search("Procure set health",3,0).hits[0].match_line==3);
  CHECK(idx.search("render menu",3,0).hits[0].path=="web/app.js");
  CHECK(idx.search("CarregarConta",3,0).hits[0].path=="script/login.pwn");
  CHECK(idx.search("`ola`",3,1).hits[0].text.find("ação")!=std::string::npos);
  put(root/"ranking/sample.py", "# RankTarget mentioned in comment\nmessage = \"RankTarget()\"\nRankTarget()\ndef RankTarget():\n    return 1\n");
  edgeai::CodeIndex ranked(root.string());auto ranked_hits=ranked.search("RankTarget",4,0);
  CHECK(ranked_hits.hits.size()>=2);CHECK(ranked_hits.hits[0].path=="ranking/sample.py");CHECK(ranked_hits.hits[0].match_line==4);
  bool saw_call=false;for(const auto& h:ranked_hits.hits)if(h.path=="ranking/sample.py"&&h.match_line==3)saw_call=true;CHECK(saw_call);
  CHECK(idx.search("totallyMissingSymbol",3,1).hits.empty());
  CHECK(idx.search("secretToken",3,1).hits.empty());
  CHECK(idx.search("dependencySecret",3,1).hits.empty());
  CHECK(idx.search("onde fica a função",3,1).hits.empty());
  fails([&]{idx.search("x",0,0);});fails([&]{idx.search("x",100,0);});
  fails([&]{idx.search(std::string(513,'a'),1,0);});
  fails([&]{edgeai::CodeIndex bad((root/"missing").string());});
  put(root/"forged\nlocation.py","def MisleadingPath(): pass\n");
  CHECK(edgeai::CodeIndex(root.string()).search("MisleadingPath").hits.empty());
  edgeai::SearchLimits limits;limits.max_file_bytes=8;
  edgeai::CodeIndex small(root.string(),limits);CHECK(small.search("SpawnPlayer").partial);
  limits=edgeai::SearchLimits{};limits.max_files=1;
  CHECK(edgeai::CodeIndex(root.string(),limits).search("x").partial);
  limits=edgeai::SearchLimits{};limits.max_total_bytes=20;
  CHECK(edgeai::CodeIndex(root.string(),limits).search("x").partial);
  edgeai::Engine e(edgeai::Mode::Eco,":memory:");
  CHECK(e.ask("buscar codigo: SpawnPlayer").text.find("code-root")!=std::string::npos);
  e.set_code_root(root.string());auto answer=e.ask("buscar codigo: SpawnPlayer");
  CHECK(!answer.neural_used);CHECK(answer.text.find("src/player.cpp:2")!=std::string::npos);
  put(root/"src/player.cpp","void DifferentNow() {}\n");
  CHECK(e.ask("buscar codigo: DifferentNow").text.find("DifferentNow")!=std::string::npos);
  fs::remove_all(root);std::cout<<"code search contracts passed\n";return 0;
 }catch(...){fs::remove_all(root);throw;}
}
