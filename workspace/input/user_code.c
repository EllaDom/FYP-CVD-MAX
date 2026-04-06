
#include <stdio.h>

int cirrus_bitblt_solidfill(int a0, int a1) {
    int x = 0;
    for (int i = 0; i < 10; i++) x += i;
    return x;
}

int main() {
    char buf[1024];
    fgets(buf, sizeof(buf), stdin);
    cirrus_bitblt_solidfill(0, 0);
    return 0;
}
