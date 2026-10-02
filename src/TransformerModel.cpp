#include "edgeai/TransformerModel.hpp"
#include "edgeai/Binary.hpp"
#include <cmath>
#include <cstring>
#include <fstream>
#include <random>
#include <stdexcept>
namespace edgeai { namespace {
constexpr char MAGIC[8]={'E','D','G','E','A','I','5','\0'};
constexpr char MAGIC6[8]={'E','D','G','E','A','I','6','\0'};
constexpr char MAGIC7[8]={'E','D','G','E','A','I','7','\0'};
template<class T>void wr(std::ostream&o,T v){o.write(reinterpret_cast<const char*>(&v),sizeof(v));if(!o)throw std::runtime_error("Transformer write failed");}
template<class T>T rd(std::istream&i){T v{};i.read(reinterpret_cast<char*>(&v),sizeof(v));if(!i)throw std::runtime_error("truncated Transformer header");return v;}
bool config_valid(const TransformerConfig&c){return c.dim>=4&&c.dim<=2048&&c.dim%2==0&&c.hidden>=4&&c.hidden<=8192&&c.window>=1&&c.window<=4096&&c.max_generate>=1&&c.max_generate<=4096&&std::isfinite(c.rope_base)&&c.rope_base>1;}
}
bool TransformerModel::valid()const{
    auto c=config;auto shape=[](const MixedMatrix&m,std::size_t r,std::size_t k){return m.rows()==r&&m.cols()==k;};
    return config_valid(c)&&embedding.size()==tokenizer.vocab_size()*c.dim&&binary::finite(embedding.data(),embedding.size())&&
        shape(query,c.dim,c.dim)&&shape(key,c.dim,c.dim)&&shape(value,c.dim,c.dim)&&shape(project,c.dim,c.dim)&&
        shape(up,c.hidden,c.dim)&&shape(down,c.dim,c.hidden)&&shape(output,tokenizer.vocab_size(),c.dim);
}
std::size_t TransformerModel::weight_bytes()const{
    std::size_t total=embedding.size()*4;for(const auto*m:{&query,&key,&value,&project,&up,&down,&output})total+=m->storage_bytes();return total;
}
std::size_t TransformerModel::parameter_count()const{
    std::size_t total=embedding.size();for(const auto*m:{&query,&key,&value,&project,&up,&down,&output})total+=m->weight_count()+m->rows();return total;
}
std::size_t TransformerModel::state_payload_bytes()const{return 8ull*config.window*config.dim;}
void TransformerModel::save(const std::string&path)const{
    if(!valid())throw std::runtime_error("invalid Transformer model");
    binary::little_endian();std::ofstream o(path,std::ios::binary);if(!o)throw std::runtime_error("cannot write Transformer");
    o.write(tokenizer.has_eos()?MAGIC7:tokenizer.has_bos()?MAGIC6:MAGIC,8);wr(o,std::uint32_t(tokenizer.has_eos()?7:tokenizer.has_bos()?6:5));for(auto n:{config.dim,config.hidden,config.window,config.max_generate})wr(o,n);wr(o,config.rope_base);
    if(tokenizer.has_bos()){wr(o,std::uint32_t(tokenizer.merges().size()));for(auto p:tokenizer.merges()){wr(o,p.first);wr(o,p.second);}}
    wr(o,std::uint64_t(embedding.size()));o.write(reinterpret_cast<const char*>(embedding.data()),static_cast<std::streamsize>(embedding.size()*4));
    for(const auto*m:{&query,&key,&value,&project,&up,&down,&output})m->save(o);
}
TransformerModel TransformerModel::load(const std::string&path){
    binary::little_endian();std::ifstream i(path,std::ios::binary);if(!i)throw std::runtime_error("cannot open model: "+path);
    char magic[8]{};i.read(magic,8);auto version=rd<std::uint32_t>(i);
    if(!((version==5&&std::memcmp(magic,MAGIC,8)==0)||(version==6&&std::memcmp(magic,MAGIC6,8)==0)||(version==7&&std::memcmp(magic,MAGIC7,8)==0)))throw std::runtime_error("not an EDGEAI5/6/7 Transformer");
    TransformerModel m;auto&c=m.config;c.dim=rd<std::uint32_t>(i);c.hidden=rd<std::uint32_t>(i);c.window=rd<std::uint32_t>(i);c.max_generate=rd<std::uint32_t>(i);c.rope_base=rd<float>(i);
    if(!config_valid(c))throw std::runtime_error("invalid Transformer config");
    if(version>=6){auto count=rd<std::uint32_t>(i);if(count>4096-(version==7?259:257))throw std::runtime_error("BPE merge limit exceeded");binary::remaining(i,count*8ull);std::vector<ByteBPE::Pair> merges;merges.reserve(count);for(std::uint32_t j=0;j<count;++j){auto a=rd<std::uint32_t>(i);auto b=rd<std::uint32_t>(i);merges.emplace_back(a,b);}m.tokenizer=ByteBPE(std::move(merges),version==7);}
    auto n=rd<std::uint64_t>(i);if(n!=m.tokenizer.vocab_size()*c.dim)throw std::runtime_error("invalid Transformer embedding");binary::remaining(i,std::size_t(n)*4);
    m.embedding.resize(std::size_t(n));i.read(reinterpret_cast<char*>(m.embedding.data()),static_cast<std::streamsize>(n*4));
    for(auto*p:{&m.query,&m.key,&m.value,&m.project,&m.up,&m.down,&m.output})*p=MixedMatrix::load(i);
    if(!m.valid())throw std::runtime_error("invalid Transformer tensors");
    if(i.peek()!=std::char_traits<char>::eof())throw std::runtime_error("trailing Transformer payload");
    return m;
}
bool is_transformer_file(const std::string&path){std::ifstream i(path,std::ios::binary);char m[8]{};i.read(m,8);if(!i)throw std::runtime_error("cannot read model header");return std::memcmp(m,MAGIC,8)==0||std::memcmp(m,MAGIC6,8)==0||std::memcmp(m,MAGIC7,8)==0;}
TransformerModel make_transformer_demo(std::uint32_t d,std::uint32_t h,std::uint32_t w){
    TransformerModel m;m.config.dim=d;m.config.hidden=h;m.config.window=w;if(!config_valid(m.config))throw std::invalid_argument("invalid demo config");
    std::mt19937 rng(122);std::normal_distribution<float> n(0,.1f);
    m.embedding.resize(256ull*d);for(auto&v:m.embedding)v=n(rng);
    auto layer=[&](std::size_t rows,std::size_t cols){DenseMatrix a(rows,cols);for(std::size_t r=0;r<rows;++r)for(std::size_t c=0;c<cols;++c)a.weight(r,c)=n(rng);return MixedMatrix(std::move(a));};
    m.query=layer(d,d);m.key=layer(d,d);m.value=layer(d,d);m.project=layer(d,d);m.up=layer(h,d);m.down=layer(d,h);m.output=layer(256,d);return m;
}
}
