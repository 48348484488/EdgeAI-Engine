#include "edgeai/ByteBPE.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <unordered_set>
namespace edgeai {namespace {
int category(unsigned char c){if((c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_')return 0;if(c>='0'&&c<='9')return 1;if(c==' '||c=='\t')return 2;if(c=='\r'||c=='\n')return 3;return 4;}
std::uint64_t key(std::uint32_t a,std::uint32_t b){return (std::uint64_t(a)<<32)|b;}
}
ByteBPE::ByteBPE(){pieces_.reserve(256);for(int i=0;i<256;++i)pieces_.push_back(std::string(1,char(i)));}
ByteBPE::ByteBPE(std::vector<Pair> merges,bool instruction):ByteBPE(){
    instruction_=instruction;
    if(merges.size()>4096-(instruction?259:257))throw std::invalid_argument("too many BPE merges");
    bos_=true;std::unordered_set<std::string> seen(pieces_.begin(),pieces_.end());
    for(auto p:merges){auto n=pieces_.size();if(p.first>=n||p.second>=n)throw std::invalid_argument("invalid merge dependency");
        auto s=pieces_[p.first]+pieces_[p.second];int cat=category(static_cast<unsigned char>(s[0]));
        if(s.size()>64||cat==3||std::any_of(s.begin(),s.end(),[&](unsigned char c){return category(c)!=cat;})||!seen.insert(s).second)
            throw std::invalid_argument("duplicate, oversized or boundary-crossing BPE piece");
        if(!ranks_.emplace(key(p.first,p.second),static_cast<std::uint32_t>(n)).second)throw std::invalid_argument("duplicate merge");
        pieces_.push_back(std::move(s));
    }
    merges_=std::move(merges);
}
std::uint32_t ByteBPE::bos_id()const{if(!bos_)throw std::logic_error("legacy tokenizer has no BOS");return static_cast<std::uint32_t>(pieces_.size());}
std::uint32_t ByteBPE::response_id()const{if(!instruction_)throw std::logic_error("no RESPONSE token");return bos_id()+1;}
std::uint32_t ByteBPE::eos_id()const{if(!instruction_)throw std::logic_error("no EOS token");return bos_id()+2;}
std::vector<std::uint32_t> ByteBPE::encode_prompt(const std::string&raw)const{
    auto ids=encode(raw,bos_);if(instruction_)ids.push_back(response_id());return ids;
}
const std::string&ByteBPE::piece(std::uint32_t token)const{
    if(bos_&&token>=pieces_.size()&&token<vocab_size()){static const std::string empty;return empty;}
    if(token>=pieces_.size()) {
        throw std::out_of_range("token out of vocabulary");
    }
    return pieces_[token];
}
std::vector<std::uint32_t> ByteBPE::encode(const std::string&raw,bool add_bos)const{
    if(raw.size()>8*1024*1024)throw std::invalid_argument("tokenizer input limit 8 MiB");
    std::vector<std::uint32_t> out;out.reserve(raw.size()+1);if(add_bos)out.push_back(bos_id());
    if(merges_.empty()){for(unsigned char c:raw)out.push_back(c);return out;}
    std::vector<std::uint32_t> ids,tmp;
    for(std::size_t start=0;start<raw.size();){
        auto end=start+1;int cat=category(static_cast<unsigned char>(raw[start]));
        if(cat!=3)while(end<raw.size()&&category(static_cast<unsigned char>(raw[end]))==cat)++end;
        ids.clear();for(auto i=start;i<end;++i)ids.push_back(static_cast<unsigned char>(raw[i]));
        while(ids.size()>1){auto best=std::numeric_limits<std::uint32_t>::max();std::uint32_t a=0,b=0;
            for(std::size_t i=1;i<ids.size();++i){auto it=ranks_.find(key(ids[i-1],ids[i]));if(it!=ranks_.end()&&it->second<best){best=it->second;a=ids[i-1];b=ids[i];}}
            if(best==std::numeric_limits<std::uint32_t>::max())break;
            tmp.clear();for(std::size_t i=0;i<ids.size();){if(i+1<ids.size()&&ids[i]==a&&ids[i+1]==b){tmp.push_back(best);i+=2;}else tmp.push_back(ids[i++]);}ids.swap(tmp);
        }
        out.insert(out.end(),ids.begin(),ids.end());start=end;
    }
    return out;
}
std::string ByteBPE::decode(const std::vector<std::uint32_t>&ids)const{std::string out;for(auto t:ids){auto&s=piece(t);if(out.size()+s.size()>64*1024*1024)throw std::invalid_argument("decoded output limit 64 MiB");out+=s;}return out;}
}
