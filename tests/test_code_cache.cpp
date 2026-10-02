#include "edgeai/CodeSearch.hpp"
#include "edgeai/Engine.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <type_traits>
#include <utility>
#define CHECK(x) do { if(!(x)) throw std::runtime_error("CHECK failed: " #x); } while(false)
namespace fs=std::filesystem;
void put(const fs::path&p,const std::string&s){fs::create_directories(p.parent_path());std::ofstream f(p,std::ios::binary);f<<s;}
template<class T,class=void>struct refreshable:std::false_type{};
template<class T>struct refreshable<T,std::void_t<decltype(std::declval<T&>().refresh())>>:std::true_type{};
template<class T>void contracts(const fs::path&root){
 if constexpr(!refreshable<T>::value){throw std::runtime_error("missing verified refresh/cache API");}
 else{
  put(root/"src/a.cpp","void AlphaThing() {}\nvoid CommonThing() {}\n");
  put(root/"src/b.cpp","void BetaThing() {}\n");
  T idx(root.string());auto a=idx.search("AlphaThing");
  CHECK(a.hits.size()==1&&a.hits[0].match_line==1);
  CHECK(a.reindexed_files==2&&a.reused_files==0&&a.revision==1);
  idx.refresh();a=idx.search("AlphaThing");
  CHECK(a.reindexed_files==0&&a.reused_files==2&&a.revision==1);
  CHECK(a.content_bytes_read==a.scanned_bytes);CHECK(a.candidate_lines==1);
  // An edit with exactly the same length and restored timestamp must invalidate.
  auto stamp=fs::last_write_time(root/"src/a.cpp");
  put(root/"src/a.cpp","void GammaThing() {}\nvoid CommonThing() {}\n");
  fs::last_write_time(root/"src/a.cpp",stamp);idx.refresh();
  CHECK(idx.search("AlphaThing").hits.empty());a=idx.search("GammaThing");
  CHECK(a.hits.size()==1&&a.reindexed_files==1&&a.reused_files==1&&a.revision==2);
  put(root/"src/new.py","def NewFunction():\n    return 1\n");fs::remove(root/"src/b.cpp");idx.refresh();
  CHECK(idx.search("BetaThing").hits.empty());CHECK(idx.search("NewFunction").hits[0].path=="src/new.py");
  // Path terms may satisfy some of the query, but at least one term must match a row.
  CHECK(idx.search("src Gamma Thing").hits.size()==1);CHECK(idx.search("src").hits.empty());
  put(root/"src/a.cpp","// shifted\n\nvoid GammaThing() {}\n");idx.refresh();
  CHECK(idx.search("GammaThing").hits[0].match_line==3);
  std::error_code ec;fs::remove(root/"src/a.cpp");fs::create_symlink(root/"src/new.py",root/"src/a.cpp",ec);
  if(!ec){idx.refresh();CHECK(idx.search("GammaThing").hits.empty());CHECK(idx.search("NewFunction").hits.size()==1);}
  fs::remove(root/"src/a.cpp",ec);put(root/"src/new.py",std::string("a\0b",3));idx.refresh();
  CHECK(idx.search("NewFunction").hits.empty());
  put(root/"too_many.cpp","int alphaBeta; int gammaDelta;\n");
  auto limits=edgeai::SearchLimits{};
  // This field is dependent so the old implementation still compiles the RED gate.
  auto bounded_limits=[&](auto l){l.max_index_entries=1;return l;};
  T bounded(root.string(),bounded_limits(limits));CHECK(bounded.search("alphaBeta").partial);
  CHECK(bounded.search("alphaBeta").hits.empty());
  fs::remove_all(root);bool rejected=false;try{idx.refresh();}catch(const std::exception&){rejected=true;}
  CHECK(rejected); // A failed refresh must not be followed by a stale answer in Engine.
 }
}
int main(){auto root=fs::temp_directory_path()/("edge-cache-"+std::to_string(std::chrono::high_resolution_clock::now().time_since_epoch().count()));
 fs::create_directories(root);try{contracts<edgeai::CodeIndex>(root);std::cout<<"cache contracts passed\n";}
 catch(const std::exception&e){fs::remove_all(root);std::cerr<<e.what()<<'\n';return 1;}
 fs::remove_all(root);return 0;}
