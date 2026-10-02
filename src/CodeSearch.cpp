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

std::vector<std::string> project_source_lines(const std::vector<std::string>& lines,const std::string& path){
 std::vector<std::string> out;out.reserve(lines.size());
 const auto ext=lower(fs::path(path).extension().string());const bool python=ext==".py"||ext==".pyi";
 bool block=false,triple=false;char triple_quote=0;
 for(const auto& line:lines){
  std::string code=line;bool single=false,dbl=false,escape=false;
  for(std::size_t i=0;i<line.size();++i){
   const char c=line[i],next=i+1<line.size()?line[i+1]:'\0';
   if(python&&triple){
    code[i]=' ';
    if(i+2<line.size()&&line[i]==triple_quote&&line[i+1]==triple_quote&&line[i+2]==triple_quote){code[i+1]=code[i+2]=' ';i+=2;triple=false;}
    continue;
   }
   if(!python&&block){code[i]=' ';if(c=='*'&&next=='/'){code[i+1]=' ';++i;block=false;}continue;}
   if(single||dbl){code[i]=' ';if(escape){escape=false;continue;}if(c=='\\'){escape=true;continue;}if((single&&c=='\'')||(dbl&&c=='"'))single=dbl=false;continue;}
   if(python&&i+2<line.size()&&((c=='"'&&line[i+1]=='"'&&line[i+2]=='"')||(c=='\''&&line[i+1]=='\''&&line[i+2]=='\''))){triple=true;triple_quote=c;code[i]=code[i+1]=code[i+2]=' ';i+=2;continue;}
   if(c=='/'&&next=='/'){std::fill(code.begin()+static_cast<std::ptrdiff_t>(i),code.end(),' ');break;}
   if(!python&&c=='/'&&next=='*'){code[i]=code[i+1]=' ';++i;block=true;continue;}
   if(python&&c=='#'){std::fill(code.begin()+static_cast<std::ptrdiff_t>(i),code.end(),' ');break;}
   if(c=='\''){code[i]=' ';single=true;continue;}
   if(c=='"'){code[i]=' ';dbl=true;continue;}
  }
  out.push_back(std::move(code));
 }
 return out;
}
std::string ltrim_copy(std::string value){auto p=value.find_first_not_of(" \t");return p==std::string::npos?std::string():value.substr(p);}
bool boundary_after(const std::string& value,std::size_t p){return p>=value.size()||!word(static_cast<unsigned char>(value[p]));}
bool control_prefix(const std::string& value){
 return value.rfind("if ",0)==0||value.rfind("if(",0)==0||value.rfind("for ",0)==0||value.rfind("for(",0)==0||
        value.rfind("while ",0)==0||value.rfind("while(",0)==0||value.rfind("switch ",0)==0||
        value.rfind("return ",0)==0||value.rfind("throw ",0)==0;
}
bool explicit_definition(const std::string& code,const std::set<std::string>& terms){
 const auto t=ltrim_copy(lower(code));
 static const std::vector<std::string> prefixes={"def ","async def ","class ","function ","fn ","func ","stock ","public "};
 for(const auto& term:terms){
  for(const auto& prefix:prefixes){auto p=t.find(prefix+term);if(p!=std::string::npos&&boundary_after(t,p+prefix.size()+term.size()))return true;}
  for(const auto& kw:{std::string("const "),std::string("let "),std::string("var ")}){
   auto p=t.find(kw+term);if(p!=std::string::npos&&boundary_after(t,p+kw.size()+term.size())&&t.find("=>",p)!=std::string::npos)return true;
  }
  auto pos=t.find(term);
  while(pos!=std::string::npos){
   if((pos==0||!word(static_cast<unsigned char>(t[pos-1])))&&boundary_after(t,pos+term.size())){
    auto n=pos+term.size();while(n<t.size()&&(t[n]==' '||t[n]=='\t'))++n;
    if(n<t.size()&&t[n]=='('&&!control_prefix(t)&&t.find('{',n)!=std::string::npos&&pos>0)return true;
   }
   pos=t.find(term,pos+term.size());
  }
 }
 return false;
}
bool declaration_like(const std::string& code,const std::set<std::string>& terms){
 const auto t=ltrim_copy(lower(code));if(t.empty()||t.back()!=';'||control_prefix(t))return false;
 for(const auto& term:terms){auto pos=t.find(term);while(pos!=std::string::npos){
  if((pos==0||!word(static_cast<unsigned char>(t[pos-1])))&&boundary_after(t,pos+term.size())){
   auto n=pos+term.size();while(n<t.size()&&(t[n]==' '||t[n]=='\t'))++n;
   if(n<t.size()&&t[n]=='('&&pos>0)return true;
  }
  pos=t.find(term,pos+term.size());
 }}
 return false;
}

} // namespace
CodeIndex::CodeIndex(const std::string& root,SearchLimits limits):limits_(limits){
 if(!limits.max_files||limits.max_files>100000||!limits.max_file_bytes||
    limits.max_file_bytes>64*1024*1024||!limits.max_total_bytes||
    limits.max_total_bytes>256*1024*1024||!limits.max_lines||
    !limits.max_depth||!limits.max_index_entries)
  throw std::invalid_argument("invalid or excessive search limits");
 root_=fs::absolute(fs::u8path(root)).generic_u8string();refresh();
}
void CodeIndex::refresh(){
 const auto& limits=limits_;CodeSearchResult next;
 fs::path base=fs::u8path(root_);std::error_code ec;
 if(fs::is_symlink(fs::symlink_status(base,ec))||!fs::is_directory(base,ec))
  throw std::invalid_argument("code root must be a real directory (not symlink)");
 base=fs::canonical(base);std::vector<fs::path> paths;
 fs::recursive_directory_iterator it(base,fs::directory_options::none,ec),end;
 if(ec)throw std::runtime_error("cannot traverse code root");
 std::size_t visited=0;
 while(it!=end){
  if(++visited>limits.max_files*20+1000){next.partial=true;break;}
  const auto p=it->path();auto status=it->symlink_status(ec);
  if(ec){next.partial=true;++next.skipped_files;ec.clear();}
  else if(fs::is_symlink(status)||excluded(p)){it.disable_recursion_pending();++next.skipped_files;}
  else if(fs::is_directory(status)&&static_cast<std::size_t>(it.depth())>=limits.max_depth){it.disable_recursion_pending();++next.skipped_files;next.partial=true;}
  else if(fs::is_regular_file(status)&&source_extension(p)){
   if(paths.size()>=limits.max_files){next.partial=true;break;}paths.push_back(p);
  }else if(!fs::is_directory(status))++next.skipped_files;
  it.increment(ec);if(ec){next.partial=true;++next.skipped_files;ec.clear();}
 }
 std::sort(paths.begin(),paths.end());
 std::unordered_map<std::string,std::shared_ptr<const Source>> previous;
 for(const auto& src:sources_)previous.emplace(src->path,src);
 std::vector<std::shared_ptr<const Source>> updated;
 for(const auto& p:paths){
  ec.clear();auto stat=fs::symlink_status(p,ec);
  if(ec||!fs::is_regular_file(stat)){++next.skipped_files;next.partial=true;continue;}
  auto size=fs::file_size(p,ec);
  if(ec||size>limits.max_file_bytes||size>limits.max_total_bytes-next.scanned_bytes){++next.skipped_files;next.partial=true;continue;}
  std::ifstream f(p,std::ios::binary);if(!f){++next.skipped_files;next.partial=true;continue;}
  std::string text(static_cast<std::size_t>(size)+1,'\0');
  f.read(text.data(),static_cast<std::streamsize>(text.size()));text.resize(static_cast<std::size_t>(f.gcount()));
  next.content_bytes_read+=text.size();
  if(f.bad()||text.size()!=size){++next.skipped_files;next.partial=true;continue;}
  auto name=p.lexically_relative(base).generic_u8string();
  const auto old=previous.find(name);
  std::shared_ptr<const Source> source;
  if(old!=previous.end()&&old->second->raw==text){
   source=old->second;
   if(source->lines.size()>limits.max_lines-next.total_lines||source->entries>limits.max_index_entries-next.index_entries){++next.skipped_files;next.partial=true;continue;}
   ++next.reused_files;
  }else{
   if(!utf8_text(text)||!utf8_text(name)||std::any_of(name.begin(),name.end(),[](unsigned char c){return c<32||c==127;})){++next.skipped_files;continue;}
   auto fresh=std::make_shared<Source>();fresh->path=name;fresh->raw=std::move(text);fresh->path_terms=tokens(name);
   std::istringstream input(fresh->raw);std::string line;bool oversize=false;
   while(std::getline(input,line)){
    if(!line.empty()&&line.back()=='\r')line.pop_back();
    if(line.size()>4096||fresh->lines.size()>=limits.max_lines-next.total_lines){oversize=true;break;}
    auto terms=tokens(line);
    if(terms.size()>limits.max_index_entries-next.index_entries-fresh->entries){oversize=true;break;}
    for(const auto& term:terms)fresh->postings[term].push_back(fresh->lines.size());
    fresh->entries+=terms.size();fresh->lines.push_back(std::move(line));
   }
   if(oversize){++next.skipped_files;next.partial=true;continue;}
   fresh->code_lines=project_source_lines(fresh->lines,name);
   source=std::move(fresh);++next.reindexed_files;
  }
  next.total_lines+=source->lines.size();next.index_entries+=source->entries;
  next.scanned_bytes+=source->raw.size();++next.scanned_files;updated.push_back(std::move(source));
 }
 bool changed=updated.size()!=sources_.size();
 if(!changed)for(std::size_t i=0;i<updated.size();++i)if(updated[i]!=sources_[i]){changed=true;break;}
 next.revision=stats_.revision+((changed||stats_.revision==0)?1:0);
 // Publish only after a complete successful refresh. Old objects are then freed.
 sources_.swap(updated);stats_=std::move(next);
}
CodeSearchResult CodeIndex::search(const std::string& query,std::size_t limit,std::size_t context)const{
 if(query.size()>512||!utf8_text(query))throw std::invalid_argument("query must be UTF-8 text of at most 512 bytes");
 if(limit<1||limit>20||context>10)throw std::invalid_argument("limit 1..20 and context 0..10 required");
 auto result=stats_;auto terms=query_tokens(query);if(terms.empty())return result;
 for(const auto& ptr:sources_){
  const auto& src=*ptr;const std::vector<std::size_t>* rarest=nullptr;bool impossible=false;
  for(const auto&term:terms){
   if(src.path_terms.count(term))continue;
   auto found=src.postings.find(term);
   if(found==src.postings.end()){impossible=true;break;}
   if(!rarest||found->second.size()<rarest->size())rarest=&found->second;
  }
  if(impossible)continue;
  std::vector<std::size_t> from_paths;
  if(!rarest){
   for(const auto&term:terms){auto f=src.postings.find(term);if(f!=src.postings.end())from_paths.insert(from_paths.end(),f->second.begin(),f->second.end());}
   std::sort(from_paths.begin(),from_paths.end());from_paths.erase(std::unique(from_paths.begin(),from_paths.end()),from_paths.end());rarest=&from_paths;
  }
  std::vector<CodeHit> local_hits;
  for(auto i:*rarest){
   ++result.candidate_lines;bool all=true;std::size_t matched_row=0;
   for(const auto&term:terms){auto f=src.postings.find(term);
    if(f!=src.postings.end()&&std::binary_search(f->second.begin(),f->second.end(),i))++matched_row;
    else if(!src.path_terms.count(term)){all=false;break;}
   }
   if(!all||!matched_row)continue;
   double score=double(matched_row)*10.0;const auto line_lower=lower(src.lines[i]);
   const auto& code=src.code_lines[i];const auto code_lower=lower(code);std::size_t code_matches=0;
   for(const auto&term:terms){
    auto pos=line_lower.find(term);if(pos!=std::string::npos){auto paren=line_lower.find('(',pos);if(paren!=std::string::npos&&pos<paren)score+=2;}
    if(code_lower.find(term)!=std::string::npos)++code_matches;
   }
   if(!code_matches)score-=8;else score+=double(code_matches);
   if(explicit_definition(code,terms))score+=12;else if(declaration_like(code,terms))score+=6;
   const auto first=line_lower.find_first_not_of(" \t");
   if(first!=std::string::npos&&(line_lower.compare(first,2,"//")==0||line_lower[first]=='#'))score-=3;
   CodeHit hit;hit.path=src.path;hit.match_line=i+1;hit.start_line=(i>context?i-context:0)+1;hit.end_line=std::min(src.lines.size(),i+context+1);hit.score=score;
   for(std::size_t n=hit.start_line-1;n<hit.end_line;++n){if(n>hit.start_line-1)hit.text+='\n';hit.text+=src.lines[n];}
   local_hits.push_back(std::move(hit));
  }
  std::sort(local_hits.begin(),local_hits.end(),[](const CodeHit&a,const CodeHit&b){if(a.score!=b.score)return a.score>b.score;return a.match_line<b.match_line;});
  const auto per_file=std::min<std::size_t>(3,limit);if(local_hits.size()>per_file)local_hits.resize(per_file);
  for(auto& hit:local_hits)result.hits.push_back(std::move(hit));
 }
 std::sort(result.hits.begin(),result.hits.end(),[](const CodeHit&a,const CodeHit&b){if(a.score!=b.score)return a.score>b.score;if(a.path!=b.path)return a.path<b.path;return a.match_line<b.match_line;});
 if(result.hits.size()>limit)result.hits.resize(limit);
 return result;
}
std::string format_code_result(const CodeSearchResult&r){
 std::ostringstream o;if(r.hits.empty())o<<"Nenhum trecho encontrado nos arquivos inspecionados. Isso nao prova que a funcao nao existe.\n";
 for(const auto& h:r.hits){o<<h.path<<":"<<h.match_line<<" (trecho "<<h.start_line<<"-"<<h.end_line<<")\n";std::istringstream s(h.text);std::string line;auto n=h.start_line;while(std::getline(s,line))o<<n++<<" | "<<line<<'\n';}
 o<<"[busca lexical; arquivos="<<r.scanned_files<<" ignorados="<<r.skipped_files<<" parcial="<<(r.partial?"sim":"nao")<<" reutilizados="<<r.reused_files<<" reindexados="<<r.reindexed_files<<" revisao="<<r.revision<<"; sem rede neural]";return o.str();
}
std::string code_result_json(const CodeSearchResult&r){
 std::ostringstream o;o<<"{\"method\":\"lexical-source-lines\",\"neural_used\":false,\"partial\":"<<(r.partial?"true":"false")<<",\"scanned_files\":"<<r.scanned_files<<",\"scanned_bytes\":"<<r.scanned_bytes<<",\"skipped_files\":"<<r.skipped_files<<",\"content_bytes_read\":"<<r.content_bytes_read<<",\"reused_files\":"<<r.reused_files<<",\"reindexed_files\":"<<r.reindexed_files<<",\"candidate_lines\":"<<r.candidate_lines<<",\"total_lines\":"<<r.total_lines<<",\"index_entries\":"<<r.index_entries<<",\"revision\":"<<r.revision<<",\"hits\":[";
 for(std::size_t i=0;i<r.hits.size();++i){if(i)o<<',';const auto&h=r.hits[i];o<<"{\"path\":"<<json_string(h.path)<<",\"match_line\":"<<h.match_line<<",\"start_line\":"<<h.start_line<<",\"end_line\":"<<h.end_line<<",\"score\":"<<h.score<<",\"text\":"<<json_string(h.text)<<'}';}
 o<<"]}";return o.str();
}
} // namespace edgeai
