#include "edgeai/CodeSearch.hpp"
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_set>
namespace edgeai { namespace {
namespace fs=std::filesystem;
std::string lower(std::string s){for(char& c:s)if(c>='A'&&c<='Z')c=char(c+32);return s;}
bool word(unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c>=128;}
bool upper(unsigned char c){return c>='A'&&c<='Z';}
bool ascii_lower(unsigned char c){return c>='a'&&c<='z';}
std::set<std::string> tokens(const std::string& s){
 std::set<std::string> out;
 for(std::size_t i=0;i<s.size();){
  if(!word(static_cast<unsigned char>(s[i]))){++i;continue;}
  std::size_t j=i+1;while(j<s.size()&&word(static_cast<unsigned char>(s[j])))++j;
  out.insert(lower(s.substr(i,j-i)));
  std::size_t start=i;
  for(std::size_t k=i;k<=j;++k){
   bool boundary=k==j||s[k]=='_'||(k>start&&upper(s[k])&&(ascii_lower(s[k-1])||(k+1<j&&ascii_lower(s[k+1]))));
   if(boundary){if(k>start)out.insert(lower(s.substr(start,k-start)));start=(k<j&&s[k]=='_')?k+1:k;}
  }
  i=j;
 }
 return out;
}
bool utf8_text(const std::string& s){
 for(std::size_t i=0;i<s.size();){
  auto c=static_cast<unsigned char>(s[i]);
  if(c<128){if(c<32&&c!='\n'&&c!='\r'&&c!='\t')return false;++i;continue;}
  std::size_t n;std::uint32_t cp,min;
  if(c>=0xc2&&c<=0xdf){n=2;cp=c&31;min=0x80;}
  else if(c>=0xe0&&c<=0xef){n=3;cp=c&15;min=0x800;}
  else if(c>=0xf0&&c<=0xf4){n=4;cp=c&7;min=0x10000;}
  else return false;
  if(i+n>s.size())return false;
  for(std::size_t k=1;k<n;++k){auto d=static_cast<unsigned char>(s[i+k]);if((d&0xc0)!=0x80)return false;cp=(cp<<6)|(d&63);}
  if(cp<min||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff))return false;
  i+=n;
 }
 return true;
}
bool excluded(const fs::path& p){
 const std::string n=lower(p.filename().u8string());
 static const std::unordered_set<std::string> names={"node_modules","vendor","dist","target","__pycache__","venv","env","bin","models","results","data","third_party","third-party","credentials.json","credentials.py","secrets.py","secret_keys.py","id_rsa","id_ed25519"};
 return n.empty()||n[0]=='.'||names.count(n)||n=="build"||n.rfind("build-",0)==0||n.rfind("build_",0)==0||n.rfind("cmake-build",0)==0;
}
bool source_extension(const fs::path& p){
 static const std::unordered_set<std::string> ext={".c",".cc",".cpp",".cxx",".h",".hh",".hpp",".hxx",".py",".pyi",".pwn",".inc",".js",".jsx",".ts",".tsx",".rs",".go",".java",".cs",".lua",".swift",".kt",".sh",".html",".css",".md",".cmake"};
 return ext.count(lower(p.extension().string()))||p.filename()=="CMakeLists.txt";
}
std::set<std::string> query_tokens(const std::string& q){
 std::string selected;bool quoted=false;
 for(std::size_t i=0;i<q.size();++i)if(q[i]=='`'||q[i]=='"'){
  auto end=q.find(q[i],i+1);if(end!=std::string::npos){selected+=' ';selected+=q.substr(i+1,end-i-1);quoted=true;i=end;}
 }
 auto t=tokens(quoted?selected:q);
 if(!quoted){
  static const std::unordered_set<std::string> stop={"a","o","as","os","de","do","da","dos","das","e","em","na","no","um","uma","para","por","que","qual","como","onde","fica","esta","está","estao","função","funcao","arquivo","codigo","código","mostre","mostrar","procure","buscar","localize","implementada","implementado","the","is","in","of","where","find","function","defined","definition","which","please","show","me"};
  for(const auto& s:stop)t.erase(s);
 }
 if(t.size()>32)throw std::invalid_argument("query has more than 32 terms");
 return t;
}
std::string json_string(const std::string& s){
 std::ostringstream o;o<<'"';
 for(unsigned char c:s){switch(c){case '"':o<<"\\\"";break;case '\\':o<<"\\\\";break;case '\n':o<<"\\n";break;case '\r':o<<"\\r";break;case '\t':o<<"\\t";break;default:if(c<32)o<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<int(c)<<std::dec;else o<<char(c);}}
 o<<'"';return o.str();
}
} // namespace
CodeIndex::CodeIndex(const std::string& root,SearchLimits limits){
 if(!limits.max_files||!limits.max_file_bytes||!limits.max_total_bytes||!limits.max_lines||!limits.max_depth)throw std::invalid_argument("search limits must be positive");
 fs::path base=fs::u8path(root);std::error_code ec;
 if(fs::is_symlink(fs::symlink_status(base,ec))||!fs::is_directory(base,ec))throw std::invalid_argument("code root must be a real directory (not symlink)");
 base=fs::canonical(base);std::vector<fs::path> paths;
 fs::recursive_directory_iterator it(base,fs::directory_options::none,ec),end;
 if(ec)throw std::runtime_error("cannot traverse code root");
 std::size_t visited=0;
 while(it!=end){
  if(++visited>limits.max_files*20+1000){stats_.partial=true;break;}
  const auto p=it->path();auto status=it->symlink_status(ec);
  if(ec){stats_.partial=true;++stats_.skipped_files;ec.clear();}
  else if(fs::is_symlink(status)||excluded(p)){it.disable_recursion_pending();++stats_.skipped_files;}
  else if(fs::is_directory(status)&&static_cast<std::size_t>(it.depth())>=limits.max_depth){it.disable_recursion_pending();++stats_.skipped_files;stats_.partial=true;}
  else if(fs::is_regular_file(status)&&source_extension(p)){
   if(paths.size()>=limits.max_files){stats_.partial=true;break;}
   paths.push_back(p);
  }else if(!fs::is_directory(status))++stats_.skipped_files;
  it.increment(ec);if(ec){stats_.partial=true;++stats_.skipped_files;ec.clear();}
 }
 std::sort(paths.begin(),paths.end());std::size_t line_count=0;
 for(const auto& p:paths){
  auto stat=fs::symlink_status(p,ec);
  if(ec||!fs::is_regular_file(stat)){++stats_.skipped_files;stats_.partial=true;continue;}
  auto size=fs::file_size(p,ec);
  if(ec||size>limits.max_file_bytes||size>limits.max_total_bytes-stats_.scanned_bytes){++stats_.skipped_files;stats_.partial=true;continue;}
  // Read at most declared size+1 so concurrent file growth cannot exhaust memory.
  std::ifstream f(p,std::ios::binary);if(!f){++stats_.skipped_files;stats_.partial=true;continue;}
  std::string text(static_cast<std::size_t>(size)+1,'\0');f.read(text.data(),static_cast<std::streamsize>(text.size()));text.resize(static_cast<std::size_t>(f.gcount()));
  if(text.size()!=size){++stats_.skipped_files;stats_.partial=true;continue;}
  auto name=p.lexically_relative(base).generic_u8string();
  if(!utf8_text(text)||!utf8_text(name)||std::any_of(name.begin(),name.end(),[](unsigned char c){return c<32||c==127;})){++stats_.skipped_files;continue;}
  Source src;src.path=name;std::istringstream input(text);std::string line;bool oversize=false;
  while(std::getline(input,line)){
   if(!line.empty()&&line.back()=='\r')line.pop_back();
   if(line.size()>4096||line_count+src.lines.size()>=limits.max_lines){oversize=true;break;}
   src.lines.push_back(line);
  }
  if(oversize){++stats_.skipped_files;stats_.partial=true;continue;}
  line_count+=src.lines.size();stats_.scanned_bytes+=text.size();++stats_.scanned_files;sources_.push_back(std::move(src));
 }
}
CodeSearchResult CodeIndex::search(const std::string& query,std::size_t limit,std::size_t context)const{
 if(query.size()>512||!utf8_text(query))throw std::invalid_argument("query must be UTF-8 text of at most 512 bytes");
 if(limit<1||limit>20||context>10)throw std::invalid_argument("limit 1..20 and context 0..10 required");
 auto result=stats_;auto terms=query_tokens(query);if(terms.empty())return result;
 for(const auto& src:sources_){
  const auto path_terms=tokens(src.path);CodeHit best;
  for(std::size_t i=0;i<src.lines.size();++i){
   auto row_tokens=tokens(src.lines[i]);bool all=true;std::size_t matched_row=0;
   for(const auto& term:terms){if(row_tokens.count(term))++matched_row;else if(!path_terms.count(term)){all=false;break;}}
   if(!all||!matched_row)continue;
   double score=double(matched_row)*10.0;const auto line_lower=lower(src.lines[i]);
   // A lexical declaration heuristic only, not AST-level symbol resolution.
   auto paren=line_lower.find('(');
   for(const auto& term:terms){auto pos=line_lower.find(term);if(pos!=std::string::npos&&paren!=std::string::npos&&pos<paren)score+=2;}
   if(line_lower.find('{')!=std::string::npos)score+=1;
   const auto first=line_lower.find_first_not_of(" \t");
   if(first!=std::string::npos&&(line_lower.compare(first,2,"//")==0||line_lower[first]=='#'))score-=3;
   if(best.match_line&&score<=best.score)continue;
   best.path=src.path;best.match_line=i+1;best.start_line=(i>context?i-context:0)+1;best.end_line=std::min(src.lines.size(),i+context+1);best.score=score;best.text.clear();
   for(std::size_t n=best.start_line-1;n<best.end_line;++n){if(n>best.start_line-1)best.text+='\n';best.text+=src.lines[n];}
  }
  if(best.match_line)result.hits.push_back(std::move(best));
 }
 std::sort(result.hits.begin(),result.hits.end(),[](const CodeHit&a,const CodeHit&b){if(a.score!=b.score)return a.score>b.score;if(a.path!=b.path)return a.path<b.path;return a.match_line<b.match_line;});
 if(result.hits.size()>limit)result.hits.resize(limit);
 return result;
}
std::string format_code_result(const CodeSearchResult&r){
 std::ostringstream o;if(r.hits.empty())o<<"Nenhum trecho encontrado nos arquivos inspecionados. Isso nao prova que a funcao nao existe.\n";
 for(const auto& h:r.hits){o<<h.path<<":"<<h.match_line<<" (trecho "<<h.start_line<<"-"<<h.end_line<<")\n";std::istringstream s(h.text);std::string line;auto n=h.start_line;while(std::getline(s,line))o<<n++<<" | "<<line<<'\n';}
 o<<"[busca lexical; arquivos="<<r.scanned_files<<" ignorados="<<r.skipped_files<<" parcial="<<(r.partial?"sim":"nao")<<"; sem rede neural]";return o.str();
}
std::string code_result_json(const CodeSearchResult&r){
 std::ostringstream o;o<<"{\"method\":\"lexical-source-lines\",\"neural_used\":false,\"partial\":"<<(r.partial?"true":"false")<<",\"scanned_files\":"<<r.scanned_files<<",\"scanned_bytes\":"<<r.scanned_bytes<<",\"skipped_files\":"<<r.skipped_files<<",\"hits\":[";
 for(std::size_t i=0;i<r.hits.size();++i){if(i)o<<',';const auto&h=r.hits[i];o<<"{\"path\":"<<json_string(h.path)<<",\"match_line\":"<<h.match_line<<",\"start_line\":"<<h.start_line<<",\"end_line\":"<<h.end_line<<",\"score\":"<<h.score<<",\"text\":"<<json_string(h.text)<<'}';}
 o<<"]}";return o.str();
}
} // namespace edgeai
