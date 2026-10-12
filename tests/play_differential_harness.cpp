// Differential behavioral validator: original compiled C vs generated C++ play.
// Both share original winner() and board. This is not independent reconstruction.
#include <cstdio>
#include <cstring>
extern "C" {
extern volatile int board[9];
int original_play(int, int);
int play(int, int);
}
static void seed_board(int state) {
    for (int j = 0; j < 9; ++j) {
        board[j] = state % 3;
        state /= 3;
    }
}
int main() {
    int cases = 0, failures = 0;
    for (int state = 0; state < 19683; ++state) {
        for (int position = -2; position <= 10; ++position) {
            for (int player = 0; player <= 2; ++player) {
                seed_board(state);
                int expected = original_play(position, player);
                int expected_board[9];
                for (int j = 0; j < 9; ++j) expected_board[j] = board[j];
                seed_board(state);
                int observed = play(position, player);
                bool equal = expected == observed;
                for (int j = 0; j < 9; ++j) equal &= expected_board[j] == board[j];
                ++cases;
                if (!equal) {
                    if (failures < 3)
                        std::fprintf(stderr, "Mismatch state=%d pos=%d player=%d expected=%d observed=%d\n",state,position,player,expected,observed);
                    ++failures;
                }
            }
        }
    }
    std::printf("{\"tested_cases\":%d,\"mismatches\":%d,\"passed\":%s}\n",
                cases,failures,failures==0?"true":"false");
    return failures ? 1 : 0;
}
