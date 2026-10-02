#include "edgeai/EdgeModel.hpp"
#include "edgeai/Binary.hpp"
#include <cmath>
#include <cstring>
#include <fstream>
#include <random>
#include <stdexcept>

namespace edgeai {
namespace {
constexpr char MAGIC[8] = {'E','D','G','E','A','I','2','\0'};
template<class T> void wr(std::ostream& o,const T& v){o.write(reinterpret_cast<const char*>(&v),sizeof(v));if(!o)throw std::runtime_error("write .edge failed");}
template<class T> T rd(std::istream& i){T v{};i.read(reinterpret_cast<char*>(&v),sizeof(v));if(!i)throw std::runtime_error("read .edge failed");return v;}
void wr_data(std::ostream&o,const void*p,std::size_t n){if(n)o.write(reinterpret_cast<const char*>(p),static_cast<std::streamsize>(n));if(!o)throw std::runtime_error("write .edge data failed");}
void rd_data(std::istream&i,void*p,std::size_t n){if(n)i.read(reinterpret_cast<char*>(p),static_cast<std::streamsize>(n));if(!i)throw std::runtime_error("read .edge data failed");}
}

bool EdgeModel::valid() const {
    const auto& c=config;
    return c.vocab_size==256 && c.dim>0 && c.dim<=4096 && c.hidden_dim>0 && c.hidden_dim<=16384 && c.default_loops>=1 && c.default_loops<=16 && c.max_generate>=1 && c.max_generate<=4096 && std::isfinite(c.early_exit_confidence) && c.early_exit_confidence>=0 && c.early_exit_confidence<=1 && embedding.size()==std::size_t(c.vocab_size)*c.dim &&
        wx.rows()==c.dim&&wx.cols()==c.dim&&wh.rows()==c.dim&&wh.cols()==c.dim&&
        reason_up.rows()==c.hidden_dim&&reason_up.cols()==c.dim&&reason_down.rows()==c.dim&&reason_down.cols()==c.hidden_dim&&
        output.rows()==c.vocab_size&&output.cols()==c.dim;
}
std::size_t EdgeModel::parameter_count() const {
    return embedding.size()+wx.weight_count()+wh.weight_count()+reason_up.weight_count()+reason_down.weight_count()+std::size_t(config.vocab_size)*config.dim;
}
std::size_t EdgeModel::resident_weight_bytes() const { return embedding.size()*sizeof(float)+wx.storage_bytes()+wh.storage_bytes()+reason_up.storage_bytes()+reason_down.storage_bytes()+output.storage_bytes(); }
std::size_t EdgeModel::fp32_equivalent_bytes() const { return parameter_count()*sizeof(float); }
double EdgeModel::compression_ratio_vs_fp32() const { const auto r=resident_weight_bytes(); return r?double(fp32_equivalent_bytes())/double(r):0.0; }

void EdgeModel::save(const std::string& path) const {
    if(!valid()) throw std::runtime_error("refusing to save invalid EdgeModel");
    std::ofstream o(path,std::ios::binary); if(!o)throw std::runtime_error("cannot open model for writing: "+path);
    wr_data(o,MAGIC,sizeof(MAGIC)); const std::uint32_t version=2;wr(o,version);
    wr(o,config.vocab_size);wr(o,config.dim);wr(o,config.hidden_dim);wr(o,config.default_loops);wr(o,config.max_generate);wr(o,config.early_exit_confidence);
    const std::uint64_t e=embedding.size();wr(o,e);wr_data(o,embedding.data(),embedding.size()*sizeof(float));
    wx.save(o);wh.save(o);reason_up.save(o);reason_down.save(o);output.save(o);
}
EdgeModel EdgeModel::load(const std::string& path){
    std::ifstream i(path,std::ios::binary);if(!i)throw std::runtime_error("cannot open .edge model: "+path);
    char magic[8]{};rd_data(i,magic,8);if(std::memcmp(magic,MAGIC,8)!=0)throw std::runtime_error("not an EdgeAI v0.2 model");
    if(rd<std::uint32_t>(i)!=2)throw std::runtime_error("unsupported .edge version");
    EdgeModel m; m.config.vocab_size=rd<std::uint32_t>(i);m.config.dim=rd<std::uint32_t>(i);m.config.hidden_dim=rd<std::uint32_t>(i);m.config.default_loops=rd<std::uint32_t>(i);m.config.max_generate=rd<std::uint32_t>(i);m.config.early_exit_confidence=rd<float>(i);
    const auto e=rd<std::uint64_t>(i); binary::little_endian(); if(m.config.vocab_size!=256||m.config.dim==0||m.config.dim>4096||e!=std::size_t(256)*m.config.dim)throw std::runtime_error("invalid embedding size");binary::remaining(i,static_cast<std::size_t>(e)*4);m.embedding.resize(static_cast<std::size_t>(e));rd_data(i,m.embedding.data(),m.embedding.size()*sizeof(float));
    m.wx=TernaryMatrix::load(i);m.wh=TernaryMatrix::load(i);m.reason_up=TernaryMatrix::load(i);m.reason_down=TernaryMatrix::load(i);m.output=DenseMatrix::load(i);
    if(!m.valid()||!binary::finite(m.embedding.data(),m.embedding.size())) throw std::runtime_error("invalid .edge tensor shapes/values");
    if(i.peek()!=std::char_traits<char>::eof())throw std::runtime_error("trailing .edge payload");
    return m;
}

EdgeModel make_demo_edge_model(std::uint32_t dim,std::uint32_t hidden){
    EdgeModel m; m.config.dim=dim;m.config.hidden_dim=hidden;m.config.default_loops=2;m.config.max_generate=48;m.config.early_exit_confidence=0.94f;
    std::mt19937 rng(7);std::normal_distribution<float> nf(0.0f,0.08f);std::uniform_int_distribution<int> ti(0,9);
    m.embedding.resize(std::size_t(256)*dim);for(auto&v:m.embedding)v=nf(rng);
    m.wx=TernaryMatrix(dim,dim);m.wh=TernaryMatrix(dim,dim);m.reason_up=TernaryMatrix(hidden,dim);m.reason_down=TernaryMatrix(dim,hidden);m.output=DenseMatrix(256,dim);
    auto fillt=[&](TernaryMatrix& a){for(std::size_t r=0;r<a.rows();++r){a.set_scale(r,0.06f);for(std::size_t c=0;c<a.cols();++c){int z=ti(rng);a.set(r,c,z<2?-1:(z<4?1:0));}}};
    fillt(m.wx);fillt(m.wh);fillt(m.reason_up);fillt(m.reason_down);
    for(std::size_t r=0;r<m.output.rows();++r){m.output.bias(r)=0.0f;for(std::size_t c=0;c<m.output.cols();++c)m.output.weight(r,c)=nf(rng);}
    // Bias the demo away from binary/control bytes so the untrained model at least emits printable text.
    for(std::size_t r=0;r<256;++r) if(r<32||r>126)m.output.bias(r)=-3.0f;
    return m;
}
}
