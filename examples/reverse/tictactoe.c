/* Jogo da velha pequeno usado para validar analise estatica ARM.
 * Sem libc; as jogadas ficam predefinidas para tornar o binario reproduzivel. */
volatile int board[9];
__attribute__((noinline)) int winner(void) {
    static const unsigned char lines[8][3] = {
        {0,1,2},{3,4,5},{6,7,8},{0,3,6},
        {1,4,7},{2,5,8},{0,4,8},{2,4,6}
    };
    for (int i=0;i<8;i++) {
        int a=board[lines[i][0]], b=board[lines[i][1]], c=board[lines[i][2]];
        if (a && a==b && b==c) return a;
    }
    return 0;
}
__attribute__((noinline)) int play(int position,int player) {
    if (position<0 || position>=9 || board[position]!=0) return -1;
    board[position]=player;
    return winner();
}
__attribute__((used)) int start(void) {
    play(0,1); play(4,2); play(1,1); play(8,2);
    return play(2,1);
}
