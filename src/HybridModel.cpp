#include "edgeai/HybridModel.hpp"
#include "edgeai/Binary.hpp"
#include <cmath>
#include <cstring>
#include <fstream>
#include <random>
#include <stdexcept>
namespace edgeai { namespace {
constexpr char MAGIC3[8]={'E','D','G','E','A','I','3','\0'};
constexpr char MAGIC4[8]={'E','D','G','E','A','I','4','\0'};
template<class T>void wr(std::ostream& o,const T& v){o.write(reinterpret_cast<const char*>(&v),sizeof(v));if(!o)throw std::runtime_error("model write failed");}
template<class T>T rd(std::istream& i){T v{};i.read(reinterpret_cast<char*>(&v),sizeof(v));if(!i)throw std::runtime_error("truncated model header");return v;}
bool config_valid(const HybridConfig& c){return c.dim>=4&&c.dim<=2048&&c.hidden>=4&&c.hidden<=8192&&c.key_dim>=1&&c.key_dim<=256&&c.window>=1&&c.window<=4096&&c.loops>=1&&c.loops<=16&&c.max_generate>=1&&c.max_generate<=4096&&std::isfinite(c.decay_logit)&&std::isfinite(c.write_logit)&&std::isfinite(c.mix_logit);}
}
bool HybridModel::valid()const{const auto& c=config;return config_valid(c)&&embedding.size()==256ull*c.dim&&binary::finite(embedding.data(),embedding.size())&&
 query.rows()==c.key_dim&&query.cols()==c.dim&&key.rows()==c.key_dim&&key.cols()==c.dim&&value.rows()==c.dim&&value.cols()==c.dim&&project.rows()==c.dim&&project.cols()==c.dim&&up.rows()==c.hidden&&up.cols()==c.dim&&down.rows()==c.dim&&down.cols()==c.hidden&&gates.rows()==3&&gates.cols()==c.dim&&output.rows()==256&&output.cols()==c.dim;}
std::size_t HybridModel::weight_bytes()const{return embedding.size()*4+query.storage_bytes()+key.storage_bytes()+value.storage_bytes()+project.storage_bytes()+up.storage_bytes()+down.storage_bytes()+gates.storage_bytes()+output.storage_bytes()+12;}
std::size_t HybridModel::parameter_count()const{
 // Count master weights + biases + learned global gates; row scales are derived.
 auto layer=[](const MixedMatrix& t){return t.weight_count()+t.rows();};
 return embedding.size()+layer(query)+layer(key)+layer(value)+layer(project)+layer(up)+layer(down)+256ull*config.dim+256+3+3*config.dim+3;
}
std::size_t HybridModel::state_payload_bytes()const{return 4ull*(config.key_dim*config.dim+config.window*(config.key_dim+config.dim));}
void HybridModel::save(const std::string& path)const{
 if(!valid())throw std::runtime_error("invalid hybrid model");
 binary::little_endian();std::ofstream o(path,std::ios::binary);if(!o)throw std::runtime_error("cannot write model");o.write(MAGIC4,8);wr(o,std::uint32_t(4));
 const auto& c=config;for(auto n:{c.dim,c.hidden,c.key_dim,c.window,c.loops,c.max_generate})wr(o,n);wr(o,c.decay_logit);wr(o,c.write_logit);wr(o,c.mix_logit);
 wr(o,std::uint64_t(embedding.size()));o.write(reinterpret_cast<const char*>(embedding.data()),static_cast<std::streamsize>(embedding.size()*4));query.save(o);key.save(o);value.save(o);project.save(o);up.save(o);down.save(o);gates.save(o);output.save(o);if(!o)throw std::runtime_error("model write failed");
}
HybridModel HybridModel::load(const std::string& path){
 binary::little_endian();std::ifstream i(path,std::ios::binary);if(!i)throw std::runtime_error("cannot open model: "+path);char magic[8]{};i.read(magic,8);auto version=rd<std::uint32_t>(i);
 if(!((version==3&&std::memcmp(magic,MAGIC3,8)==0)||(version==4&&std::memcmp(magic,MAGIC4,8)==0)))throw std::runtime_error("not a supported EDGEAI3/4 model");
 HybridModel m;m.source_format_version=version;auto& c=m.config;c.dim=rd<std::uint32_t>(i);c.hidden=rd<std::uint32_t>(i);c.key_dim=rd<std::uint32_t>(i);c.window=rd<std::uint32_t>(i);c.loops=rd<std::uint32_t>(i);c.max_generate=rd<std::uint32_t>(i);c.decay_logit=rd<float>(i);c.write_logit=rd<float>(i);c.mix_logit=rd<float>(i);
 if(!config_valid(c))throw std::runtime_error("invalid hybrid configuration");
 auto n=rd<std::uint64_t>(i);if(n!=256ull*c.dim)throw std::runtime_error("invalid embedding dimensions");binary::remaining(i,std::size_t(n)*4);m.embedding.resize(std::size_t(n));i.read(reinterpret_cast<char*>(m.embedding.data()),static_cast<std::streamsize>(n*4));
 auto load_projection=[&]()->MixedMatrix{return version==3?MixedMatrix(TernaryMatrix::load(i)):MixedMatrix::load(i);};
 m.query=load_projection();m.key=load_projection();m.value=load_projection();m.project=load_projection();m.up=load_projection();m.down=load_projection();
 m.gates=DenseMatrix::load(i);m.output=version==3?MixedMatrix(DenseMatrix::load(i)):MixedMatrix::load(i);
 if(!m.valid())throw std::runtime_error("invalid hybrid model tensors");
 if(i.peek()!=std::char_traits<char>::eof())throw std::runtime_error("trailing model payload");
 return m;
}
bool is_hybrid_file(const std::string& path){std::ifstream i(path,std::ios::binary);char magic[8]{};i.read(magic,8);if(!i)throw std::runtime_error("cannot read model header: "+path);return std::memcmp(magic,MAGIC3,8)==0||std::memcmp(magic,MAGIC4,8)==0;}
HybridModel make_hybrid_demo(std::uint32_t d,std::uint32_t k,std::uint32_t w){
 HybridModel m;m.config.dim=d;m.config.hidden=d*2;m.config.key_dim=k;m.config.window=w;
 if(!config_valid(m.config))throw std::invalid_argument("invalid demo dimensions");
 std::mt19937 rng(73);std::normal_distribution<float> f(0,.1f);std::uniform_int_distribution<int> q(-1,1);m.embedding.resize(256ull*d);for(auto&v:m.embedding)v=f(rng);
 auto random_ternary=[&](std::size_t rows,std::size_t cols){
    TernaryMatrix a(rows,cols);for(std::size_t r=0;r<rows;++r){a.set_scale(r,.08f);for(std::size_t col=0;col<cols;++col)a.set(r,col,q(rng));}return a;
 };
 m.query=random_ternary(k,d);m.key=random_ternary(k,d);m.value=random_ternary(d,d);m.project=random_ternary(d,d);m.up=random_ternary(d*2,d);m.down=random_ternary(d,d*2);m.gates=DenseMatrix(3,d);
 DenseMatrix output(256,d);for(std::size_t r=0;r<256;++r)for(std::size_t col=0;col<d;++col)output.weight(r,col)=f(rng);m.output=std::move(output);
 return m;
}
}
