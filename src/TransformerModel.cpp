#include "edgeai/TransformerModel.hpp"
#include "edgeai/Binary.hpp"
#include <cmath>
#include <cstring>
#include <fstream>
#include <random>
#include <stdexcept>
namespace edgeai { namespace {
constexpr char MAGIC5[8]={'E','D','G','E','A','I','5','\0'};
constexpr char MAGIC6[8]={'E','D','G','E','A','I','6','\0'};
constexpr char MAGIC7[8]={'E','D','G','E','A','I','7','\0'};
constexpr char MAGIC8[8]={'E','D','G','E','A','I','8','\0'};
template<class T>void wr(std::ostream&o,T v){o.write(reinterpret_cast<const char*>(&v),sizeof(v));if(!o)throw std::runtime_error("Transformer write failed");}
template<class T>T rd(std::istream&i){T v{};i.read(reinterpret_cast<char*>(&v),sizeof(v));if(!i)throw std::runtime_error("truncated Transformer header");return v;}
bool config_valid(const TransformerConfig&c){
    return c.dim>=4&&c.dim<=2048&&c.dim%2==0&&c.hidden>=4&&c.hidden<=8192&&
           c.window>=1&&c.window<=4096&&c.max_generate>=1&&c.max_generate<=4096&&
           c.blocks>=1&&c.blocks<=8&&std::isfinite(c.rope_base)&&c.rope_base>1;
}
bool shape(const MixedMatrix&m,std::size_t r,std::size_t c){return m.rows()==r&&m.cols()==c;}
bool block_valid(const TransformerBlock&b,const TransformerConfig&c){
    return shape(b.query,c.dim,c.dim)&&shape(b.key,c.dim,c.dim)&&
           shape(b.value,c.dim,c.dim)&&shape(b.project,c.dim,c.dim)&&
           shape(b.up,c.hidden,c.dim)&&shape(b.down,c.dim,c.hidden);
}
std::uint32_t tokenizer_mode(const ByteBPE&t){return t.has_eos()?2u:t.has_bos()?1u:0u;}
void save_block(std::ostream&o,const TransformerBlock&b){
    for(const auto*m:{&b.query,&b.key,&b.value,&b.project,&b.up,&b.down})m->save(o);
}
TransformerBlock load_block(std::istream&i){
    TransformerBlock b;
    for(auto*m:{&b.query,&b.key,&b.value,&b.project,&b.up,&b.down})*m=MixedMatrix::load(i);
    return b;
}
void save_embedding(std::ostream&o,const TransformerModel&m){
    wr(o,std::uint64_t(m.embedding.size()));
    o.write(reinterpret_cast<const char*>(m.embedding.data()),static_cast<std::streamsize>(m.embedding.size()*4));
    if(!o)throw std::runtime_error("Transformer write failed");
}
void load_embedding(std::istream&i,TransformerModel&m){
    auto n=rd<std::uint64_t>(i);
    if(n!=m.tokenizer.vocab_size()*m.config.dim)throw std::runtime_error("invalid Transformer embedding");
    binary::remaining(i,std::size_t(n)*4);
    m.embedding.resize(std::size_t(n));
    i.read(reinterpret_cast<char*>(m.embedding.data()),static_cast<std::streamsize>(n*4));
    if(!i)throw std::runtime_error("truncated Transformer embedding");
}
}
bool TransformerModel::valid()const{
    const auto&c=config;
    if(!config_valid(c)||blocks_data.size()!=c.blocks||
       embedding.size()!=tokenizer.vocab_size()*c.dim||
       !binary::finite(embedding.data(),embedding.size())||
       !shape(output,tokenizer.vocab_size(),c.dim))return false;
    for(const auto&b:blocks_data)if(!block_valid(b,c))return false;
    return true;
}
std::size_t TransformerModel::weight_bytes()const{
    std::size_t total=embedding.size()*4+output.storage_bytes();
    for(const auto&b:blocks_data)
        for(const auto*m:{&b.query,&b.key,&b.value,&b.project,&b.up,&b.down})total+=m->storage_bytes();
    return total;
}
std::size_t TransformerModel::parameter_count()const{
    std::size_t total=embedding.size()+output.weight_count()+output.rows();
    for(const auto&b:blocks_data)
        for(const auto*m:{&b.query,&b.key,&b.value,&b.project,&b.up,&b.down})total+=m->weight_count()+m->rows();
    return total;
}
std::size_t TransformerModel::state_payload_bytes()const{
    return 8ull*config.blocks*config.window*config.dim;
}
void TransformerModel::save(const std::string&path)const{
    if(!valid())throw std::runtime_error("invalid Transformer model");
    binary::little_endian();std::ofstream o(path,std::ios::binary);if(!o)throw std::runtime_error("cannot write Transformer");
    if(config.blocks==1){
        const auto version=tokenizer.has_eos()?7u:tokenizer.has_bos()?6u:5u;
        const char*magic=version==7?MAGIC7:version==6?MAGIC6:MAGIC5;
        o.write(magic,8);wr(o,version);
        for(auto n:{config.dim,config.hidden,config.window,config.max_generate})wr(o,n);
        wr(o,config.rope_base);
        if(version>=6){
            wr(o,std::uint32_t(tokenizer.merges().size()));
            for(auto p:tokenizer.merges()){wr(o,p.first);wr(o,p.second);}
        }
        save_embedding(o,*this);save_block(o,blocks_data.front());output.save(o);return;
    }
    o.write(MAGIC8,8);wr(o,std::uint32_t(8));
    for(auto n:{config.dim,config.hidden,config.window,config.max_generate})wr(o,n);
    wr(o,config.rope_base);wr(o,config.blocks);
    const auto mode=tokenizer_mode(tokenizer);wr(o,mode);
    const auto merge_count=std::uint32_t(tokenizer.merges().size());
    if(mode==0&&merge_count)throw std::runtime_error("raw-byte tokenizer cannot carry BPE merges");
    wr(o,merge_count);
    for(auto p:tokenizer.merges()){wr(o,p.first);wr(o,p.second);}
    save_embedding(o,*this);
    for(const auto&b:blocks_data)save_block(o,b);
    output.save(o);
}
TransformerModel TransformerModel::load(const std::string&path){
    binary::little_endian();std::ifstream i(path,std::ios::binary);if(!i)throw std::runtime_error("cannot open model: "+path);
    char magic[8]{};i.read(magic,8);auto version=rd<std::uint32_t>(i);
    const bool legacy=(version==5&&std::memcmp(magic,MAGIC5,8)==0)||
                      (version==6&&std::memcmp(magic,MAGIC6,8)==0)||
                      (version==7&&std::memcmp(magic,MAGIC7,8)==0);
    const bool multi=version==8&&std::memcmp(magic,MAGIC8,8)==0;
    if(!legacy&&!multi)throw std::runtime_error("not an EDGEAI5/6/7/8 Transformer");
    TransformerModel m;auto&c=m.config;
    c.dim=rd<std::uint32_t>(i);c.hidden=rd<std::uint32_t>(i);c.window=rd<std::uint32_t>(i);c.max_generate=rd<std::uint32_t>(i);c.rope_base=rd<float>(i);
    if(multi){
        c.blocks=rd<std::uint32_t>(i);
        if(!config_valid(c))throw std::runtime_error("invalid Transformer config");
        const auto mode=rd<std::uint32_t>(i),count=rd<std::uint32_t>(i);
        if(mode>2)throw std::runtime_error("invalid EDGEAI8 tokenizer mode");
        if((mode==0&&count!=0)||count>4096-(mode==2?259u:257u))throw std::runtime_error("BPE merge limit exceeded");
        binary::remaining(i,std::size_t(count)*8);
        std::vector<ByteBPE::Pair> merges;merges.reserve(count);
        for(std::uint32_t j=0;j<count;++j){auto a=rd<std::uint32_t>(i);auto b=rd<std::uint32_t>(i);merges.emplace_back(a,b);}
        if(mode==0)m.tokenizer=ByteBPE();
        else m.tokenizer=ByteBPE(std::move(merges),mode==2);
    }else{
        c.blocks=1;
        if(!config_valid(c))throw std::runtime_error("invalid Transformer config");
        if(version>=6){
            auto count=rd<std::uint32_t>(i);
            if(count>4096-(version==7?259:257))throw std::runtime_error("BPE merge limit exceeded");
            binary::remaining(i,std::size_t(count)*8);
            std::vector<ByteBPE::Pair> merges;merges.reserve(count);
            for(std::uint32_t j=0;j<count;++j){auto a=rd<std::uint32_t>(i);auto b=rd<std::uint32_t>(i);merges.emplace_back(a,b);}
            m.tokenizer=ByteBPE(std::move(merges),version==7);
        }
    }
    load_embedding(i,m);
    m.blocks_data.reserve(c.blocks);
    for(std::uint32_t b=0;b<c.blocks;++b)m.blocks_data.push_back(load_block(i));
    m.output=MixedMatrix::load(i);
    if(!m.valid())throw std::runtime_error("invalid Transformer tensors");
    if(i.peek()!=std::char_traits<char>::eof())throw std::runtime_error("trailing Transformer payload");
    return m;
}
bool is_transformer_file(const std::string&path){
    std::ifstream i(path,std::ios::binary);char m[8]{};i.read(m,8);if(!i)throw std::runtime_error("cannot read model header");
    return std::memcmp(m,MAGIC5,8)==0||std::memcmp(m,MAGIC6,8)==0||
           std::memcmp(m,MAGIC7,8)==0||std::memcmp(m,MAGIC8,8)==0;
}
TransformerModel make_transformer_demo(std::uint32_t d,std::uint32_t h,std::uint32_t w,std::uint32_t blocks){
    TransformerModel m;m.config.dim=d;m.config.hidden=h;m.config.window=w;m.config.blocks=blocks;
    if(!config_valid(m.config))throw std::invalid_argument("invalid demo config");
    std::mt19937 rng(122);std::normal_distribution<float> n(0,.1f);
    m.embedding.resize(256ull*d);for(auto&v:m.embedding)v=n(rng);
    auto layer=[&](std::size_t rows,std::size_t cols){DenseMatrix a(rows,cols);for(std::size_t r=0;r<rows;++r)for(std::size_t c=0;c<cols;++c)a.weight(r,c)=n(rng);return MixedMatrix(std::move(a));};
    m.blocks_data.reserve(blocks);
    for(std::uint32_t index=0;index<blocks;++index){
        TransformerBlock b;b.query=layer(d,d);b.key=layer(d,d);b.value=layer(d,d);b.project=layer(d,d);b.up=layer(h,d);b.down=layer(d,h);
        m.blocks_data.push_back(std::move(b));
    }
    m.output=layer(256,d);return m;
}
}
