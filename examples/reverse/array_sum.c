/* Additional reverse-engineering fixture unrelated to the tic-tac-toe game.
 * An optimizer may use a countdown loop and post-indexed LDR.
 */
__attribute__((noinline)) int sum_array(const int *xs, unsigned n) {
    int sum = 0;
    for (unsigned i = 0; i < n; ++i)
        sum += xs[i];
    return sum;
}
__attribute__((used)) int start(void) {
    static const int xs[4] = {1, 2, 3, 4};
    return sum_array(xs, 4);
}
