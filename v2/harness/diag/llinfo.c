/* llinfo.c: zhen's neighbour-table read (ZhenDarwin/NeighborTable.swift at 0.8.1), alone. Prints the dump's size,
 * the entries, and how many carry a hardware address. Study 2 S2 diagnostic: which processes macOS lets see it. */
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/sysctl.h>
#include <net/if_dl.h>
#include <net/route.h>
#include <netinet/in.h>
int main(void) {
    int mib[6] = {CTL_NET, PF_ROUTE, 0, AF_INET, NET_RT_FLAGS, RTF_LLINFO};
    size_t len = 0;
    if (sysctl(mib, 6, NULL, &len, NULL, 0) < 0) { perror("sysctl size"); return 1; }
    char *buf = malloc(len + 1);
    if (len && sysctl(mib, 6, buf, &len, NULL, 0) < 0) { perror("sysctl"); return 1; }
    int entries = 0, with_mac = 0;
    for (char *p = buf; p < buf + len; ) {
        struct rt_msghdr *rtm = (struct rt_msghdr *)p;
        struct sockaddr_in *sin = (struct sockaddr_in *)(rtm + 1);
        struct sockaddr_dl *sdl = (struct sockaddr_dl *)((char *)sin + ((sin->sin_len + 3) & ~3));
        entries++; if (sdl->sdl_family == AF_LINK && sdl->sdl_alen > 0) with_mac++;
        p += rtm->rtm_msglen;
    }
    printf("{\"dump_bytes\": %zu, \"entries\": %d, \"with_mac\": %d}\n", len, entries, with_mac);
    return 0;
}
