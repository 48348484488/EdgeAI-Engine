// End-to-end differential check of ALL reconstructed functions of a tiny game.
#include <cstdint>
#include <cstdio>
extern "C" volatile int board[9];
extern "C" int original_start(void);
extern "C" int start(void);

static uint32_t seed = 0x9e3779b9u;
static uint32_t next_random() {
    seed ^= seed << 13;
    seed ^= seed >> 17;
    seed ^= seed << 5;
    return seed;
}
static int checks = 0, failures = 0;
static void compare_game(const int input[9]) {
    for (int i = 0; i < 9; ++i) board[i] = input[i];
    const int expected = original_start();
    int old_board[9];
    for (int i = 0; i < 9; ++i) old_board[i] = board[i];
    for (int i = 0; i < 9; ++i) board[i] = input[i];
    const int result = start();
    bool ok = (expected == result);
    for (int i = 0; i < 9; ++i) ok &= (old_board[i] == board[i]);
    if (!ok) {
        if (failures < 3) std::fprintf(stderr,
            "Mismatch at case %d expected=%d reconstructed=%d\n", checks, expected, result);
        ++failures;
    }
    ++checks;
}
int main() {
    int input[9] = {};
    const int alphabet[4] = {-1, 0, 1, 2};
    for (int state = 0; state < 262144; ++state) {
        int encoded = state;
        for (int i = 0; i < 9; ++i) {
            input[i] = alphabet[encoded & 3];
            encoded >>= 2;
        }
        compare_game(input);
    }
    for (int k = 0; k < 16384; ++k) {
        for (int i = 0; i < 9; ++i)
            input[i] = static_cast<int32_t>(next_random());
        compare_game(input);
    }
    std::printf("{\"passed\":%s,\"tested_cases\":%d,\"mismatches\":%d}\n",
                failures ? "false" : "true", checks, failures);
    return failures ? 1 : 0;
}
