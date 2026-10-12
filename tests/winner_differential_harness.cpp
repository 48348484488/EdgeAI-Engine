// Compare original C winner() and reconstructed C++ winner() on same board.
#include <cstdint>
#include <cstdio>
extern "C" volatile int board[9];
extern "C" int original_winner(void);
extern "C" int winner(void);

static unsigned int rng = 0x9e3779b9u;
static unsigned int next_random() {
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
}
static int tests = 0;
static int mismatches = 0;
static void check(const int values[9]) {
    for (int i = 0; i < 9; ++i) board[i] = values[i];
    int expected = original_winner();
    int observed = winner();
    bool same = expected == observed;
    for (int i = 0; i < 9; ++i) same &= board[i] == values[i];
    ++tests;
    if (!same) {
        if (mismatches < 4) std::fprintf(stderr,
            "winner mismatch case=%d expected=%d observed=%d\n", tests, expected, observed);
        ++mismatches;
    }
}
int main() {
    int values[9]{};
    for (int state = 0; state < 19683; ++state) {
        int n = state;
        for (int i = 0; i < 9; ++i) { values[i] = n % 3; n /= 3; }
        check(values);
    }
    const int edge[] = {-2147483647-1, -1, 3, 2147483647};
    for (int c : edge) {
        for (int i = 0; i < 9; ++i) values[i] = c;
        check(values);
    }
    for (int k = 0; k < 65536; ++k) {
        for (int i = 0; i < 9; ++i) values[i] = static_cast<int>(next_random());
        check(values);
    }
    std::printf("{\"tested_cases\":%d,\"mismatches\":%d,\"passed\":%s}\n",
                tests, mismatches, mismatches ? "false" : "true");
    return mismatches ? 1 : 0;
}
