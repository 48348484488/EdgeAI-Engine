#include "candidate_401758.cpp"
#include <cassert>
#include <cstdio>
#include <deque>
#include <string>
#include <vector>
using namespace edgeai_2048_v23;
struct Fixture {
    std::deque<int> keys;
    std::vector<std::string> events;
    std::vector<Board> rendered;
    std::uint32_t first = 1, second = 0, move_result = 1;
    int resets = 0, moves = 0, last_move = -1, terminal_calls = 0;
    Hooks hooks() {
        Hooks h;
        h.startup = [&]{ events.push_back("start"); };
        h.reset_board = [&](Board& b){ b.fill(static_cast<std::uint8_t>(++resets)); events.push_back("reset"); };
        h.print_score = [&](std::uint32_t s){ events.push_back("score:"+std::to_string(s)); };
        h.render_board = [&](Board& b){ rendered.push_back(b); events.push_back("draw"); };
        h.render_finish = [&]{ events.push_back("finish"); };
        h.read_key = [&]()->int { assert(!keys.empty()); int k=keys.front();keys.pop_front();return k; };
        for (int i=0;i<4;++i) h.move[i] = [&,i](Board& b, std::uint32_t& s)->std::uint32_t {
            ++moves;last_move=i; events.push_back("move:"+std::to_string(i));
            b[0]=77; b[63]=88; s+=4; return move_result;
        };
        h.spawn_tile = [&](Board& b){ b[1]=55; events.push_back("spawn"); };
        h.check_first = [&](Board&){ events.push_back("check1"); return first; };
        h.check_second = [&](Board&){ events.push_back("check2"); return second; };
        h.on_first_false = [&]{ events.push_back("first_false"); };
        h.on_second_true = [&]{ events.push_back("second_true"); };
        h.terminal_mode = [&](unsigned mode){ assert(mode==1);++terminal_calls;events.push_back("terminal"); };
        return h;
    }
};
static bool contains(const std::vector<std::string>& e, const std::string& needle) {
    for(const auto& x:e) if(x==needle)return true;
    return false;
}
int main() {
    {
        Fixture f; f.keys={'q'}; assert(candidate_401758(f.hooks(),1)==0);
        assert(f.events == (std::vector<std::string>{"start","reset","score:0","draw","finish","terminal"}));
        assert(f.moves==0 && f.terminal_calls==1 && f.rendered[0][63]==1);
    }
    {
        Fixture f; f.keys={27, 'a', 'B', 'C', 'D', 'Q'}; f.move_result=0;
        assert(candidate_401758(f.hooks(),6)==0);
        assert(f.moves==3); // lowercase a ignored, uppercase B/C/D accepted.
        assert(f.last_move==3);assert(!contains(f.events,"spawn"));
        assert(f.rendered.size()==1 && f.terminal_calls==1);
    }
    {
        Fixture f; f.keys={'A','b','Q'};
        assert(candidate_401758(f.hooks(),3)==0);
        assert(f.moves==1 && contains(f.events,"spawn"));
        assert(f.rendered.size()==3);
        assert(f.rendered[1][0]==77 && f.rendered[1][1]==55 && f.rendered[1][63]==88);
        assert(f.rendered[2][0]==1 && f.rendered[2][1]==1 && f.rendered[2][63]==1);
        assert(contains(f.events,"score:4")); // Undo does not roll back score in original.
    }
    {
        Fixture f; f.keys={'R','r','Q'};
        assert(candidate_401758(f.hooks(),3)==0);
        assert(f.resets==3 && f.moves==0 && f.rendered.size()==3);
        assert(f.rendered[0][0]==1 && f.rendered[1][0]==2 && f.rendered[2][0]==3);
        int scores=0;for(const auto& e:f.events)if(e=="score:0")++scores;
        assert(scores==5); // one initial score and two per reset.
    }
    {
        Fixture f; f.keys={'A'};f.first=0;
        assert(candidate_401758(f.hooks(),1)==0);
        assert(contains(f.events,"first_false") && !contains(f.events,"check2"));
        assert(f.rendered.size()==3 && f.terminal_calls==1);
    }
    {
        Fixture f; f.keys={'C'};f.first=1;f.second=1;
        assert(candidate_401758(f.hooks(),1)==0);
        assert(contains(f.events,"second_true") && f.last_move==2);
        assert(f.rendered.size()==3 && f.terminal_calls==1);
    }
    {
        Fixture f; f.keys={'A'};f.first=1;f.second=0;
        assert(candidate_401758(f.hooks(),1)==2); // bounded host test; original keeps reading.
        assert(f.terminal_calls==0 && f.rendered.size()==2);
    }
    {
        Fixture f; f.keys={'Q'}; auto h=f.hooks();h.move[2]={};
        bool rejected=false;
        try { (void)candidate_401758(h,1); } catch (const std::invalid_argument&) { rejected=true; }
        assert(rejected);
    }
    std::puts("PASS: 8 main-loop scenario checks");
}
