#pragma once
#include <cstdint>
#include <string>
#include <utility>
#include <vector>
#include <unordered_map>
namespace edgeai {
// Default tokenizer is legacy raw bytes. Explicit merges constructor adds BOS.
class ByteBPE {
public:
    using Pair=std::pair<std::uint32_t,std::uint32_t>;
    ByteBPE();
    explicit ByteBPE(std::vector<Pair> merges,bool instruction=false);
    bool has_bos()const{return bos_;}
    bool has_eos()const{return instruction_;}
    std::uint32_t response_id()const;
    std::uint32_t eos_id()const;
    std::uint32_t bos_id()const;
    std::size_t vocab_size()const{return pieces_.size()+(bos_?1:0)+(instruction_?2:0);}
    const std::vector<Pair>& merges()const{return merges_;}
    const std::string& piece(std::uint32_t token)const;
    std::vector<std::uint32_t> encode(const std::string&raw,bool add_bos=false)const;
    std::vector<std::uint32_t> encode_prompt(const std::string&raw)const;
    std::string decode(const std::vector<std::uint32_t>&ids)const;
private:
    bool bos_=false,instruction_=false;
    std::vector<Pair> merges_;
    std::vector<std::string> pieces_;
    std::unordered_map<std::uint64_t,std::uint32_t> ranks_;
};
}
