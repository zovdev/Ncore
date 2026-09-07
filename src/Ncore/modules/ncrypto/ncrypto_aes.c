/*
 * Copyright 2026 zovdev
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "ncrypto_aes.h"

#include <stdlib.h>
#include <string.h>

#if defined(__x86_64__) || defined(__i386__) || defined(_M_X64) || defined(_M_IX86)
#  define NC_X86 1
#endif

#if defined(NC_X86)
#  if defined(_MSC_VER) && !defined(__clang__)
#    include <intrin.h>
#    define NC_AESNI_ATTR
#    define NC_HAS_AESNI 1
#  else
#    include <cpuid.h>
#    include <immintrin.h>
#    define NC_AESNI_ATTR __attribute__((target("sse2,aes")))
#    define NC_HAS_AESNI 1
#  endif
#endif

static uint8_t g_sbox[256];
static uint8_t g_isbox[256];
static uint32_t g_te0[256], g_te1[256], g_te2[256], g_te3[256];
static uint32_t g_td0[256], g_td1[256], g_td2[256], g_td3[256];

static int g_backend = NC_BACKEND_SOFT;
static nc_caps_t g_caps;

#if defined(__GNUC__) || defined(__clang__)
static int g_state = 0;
static int nc_state_load(void) { return __atomic_load_n(&g_state, __ATOMIC_ACQUIRE); }
static int nc_state_cas(void) {
    int e = 0;
    return __atomic_compare_exchange_n(&g_state, &e, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
}
static void nc_state_done(void) { __atomic_store_n(&g_state, 2, __ATOMIC_RELEASE); }
#elif defined(_MSC_VER)
static volatile long g_state = 0;
static int nc_state_load(void) { return (int)g_state; }
static int nc_state_cas(void) { return _InterlockedCompareExchange(&g_state, 1, 0) == 0; }
static void nc_state_done(void) { _InterlockedExchange(&g_state, 2); }
#else
static int g_state = 0;
static int nc_state_load(void) { return g_state; }
static int nc_state_cas(void) { if (g_state == 0) { g_state = 1; return 1; } return 0; }
static void nc_state_done(void) { g_state = 2; }
#endif

static inline uint8_t nc_xt(uint8_t a) {
    return (uint8_t)((a << 1) ^ ((a & 0x80) ? 0x1b : 0x00));
}

static inline uint8_t nc_rotl8(uint8_t u, unsigned n) {
    return (uint8_t)((uint8_t)(u << n) | (uint8_t)(u >> (8 - n)));
}

static inline uint32_t nc_ror8(uint32_t v) { return (v >> 8) | (v << 24); }
static inline uint32_t nc_ror16(uint32_t v) { return (v >> 16) | (v << 16); }
static inline uint32_t nc_ror24(uint32_t v) { return (v >> 24) | (v << 8); }

static inline uint32_t nc_ld32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static inline void nc_st32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static inline uint32_t nc_subw(uint32_t w) {
    return (uint32_t)g_sbox[w & 0xff]
         | ((uint32_t)g_sbox[(w >> 8) & 0xff] << 8)
         | ((uint32_t)g_sbox[(w >> 16) & 0xff] << 16)
         | ((uint32_t)g_sbox[w >> 24] << 24);
}

static inline uint8_t nc_mul9(uint8_t a) {
    return (uint8_t)(nc_xt(nc_xt(nc_xt(a))) ^ a);
}

static inline uint8_t nc_mul11(uint8_t a) {
    uint8_t x = nc_xt(nc_xt(nc_xt(a)));
    return (uint8_t)(x ^ nc_xt(a) ^ a);
}

static inline uint8_t nc_mul13(uint8_t a) {
    uint8_t x = nc_xt(nc_xt(nc_xt(a)));
    return (uint8_t)(x ^ nc_xt(nc_xt(a)) ^ a);
}

static inline uint8_t nc_mul14(uint8_t a) {
    uint8_t x = nc_xt(nc_xt(nc_xt(a)));
    return (uint8_t)(x ^ nc_xt(nc_xt(a)) ^ nc_xt(a));
}

static inline uint32_t nc_imcw(uint32_t w) {
    uint8_t a0 = (uint8_t)w;
    uint8_t a1 = (uint8_t)(w >> 8);
    uint8_t a2 = (uint8_t)(w >> 16);
    uint8_t a3 = (uint8_t)(w >> 24);
    return (uint32_t)(nc_mul14(a0) ^ nc_mul11(a1) ^ nc_mul13(a2) ^ nc_mul9(a3))
         | ((uint32_t)(nc_mul9(a0) ^ nc_mul14(a1) ^ nc_mul11(a2) ^ nc_mul13(a3)) << 8)
         | ((uint32_t)(nc_mul13(a0) ^ nc_mul9(a1) ^ nc_mul14(a2) ^ nc_mul11(a3)) << 16)
         | ((uint32_t)(nc_mul11(a0) ^ nc_mul13(a1) ^ nc_mul9(a2) ^ nc_mul14(a3)) << 24);
}

static inline void nc_be_inc(uint8_t *c) {
    for (int i = 15; i >= 0; i--) {
        if (++c[i]) break;
    }
}

static void nc_be_add(uint8_t *c, uint64_t n) {
    unsigned carry = 0;
    for (int i = 15; i >= 8; i--) {
        unsigned t = (unsigned)c[i] + (unsigned)(n & 0xff) + carry;
        c[i] = (uint8_t)t;
        carry = t >> 8;
        n >>= 8;
    }
    for (int i = 7; i >= 0 && carry; i--) {
        unsigned t = (unsigned)c[i] + carry;
        c[i] = (uint8_t)t;
        carry = t >> 8;
    }
}

static void nc_gen_tables(void) {
    uint8_t alog[255];
    uint8_t inv[256];
    uint8_t x = 1;
    for (unsigned i = 0; i < 255; i++) {
        alog[i] = x;
        x = (uint8_t)(nc_xt(x) ^ x);
    }
    inv[0] = 0;
    for (unsigned i = 0; i < 255; i++) {
        inv[alog[i]] = alog[(255 - i) % 255];
    }
    for (unsigned v = 0; v < 256; v++) {
        uint8_t u = inv[v];
        g_sbox[v] = (uint8_t)(u ^ nc_rotl8(u, 1) ^ nc_rotl8(u, 2) ^ nc_rotl8(u, 3) ^ nc_rotl8(u, 4) ^ 0x63);
    }
    for (unsigned v = 0; v < 256; v++) {
        g_isbox[g_sbox[v]] = (uint8_t)v;
    }
    for (unsigned v = 0; v < 256; v++) {
        uint8_t s = g_sbox[v];
        uint8_t d = g_isbox[v];
        uint32_t e = (uint32_t)nc_xt(s)
                   | ((uint32_t)s << 8)
                   | ((uint32_t)s << 16)
                   | ((uint32_t)(uint8_t)(nc_xt(s) ^ s) << 24);
        g_te0[v] = e;
        g_te1[v] = nc_ror24(e);
        g_te2[v] = nc_ror16(e);
        g_te3[v] = nc_ror8(e);
        uint32_t t = (uint32_t)nc_mul14(d)
                   | ((uint32_t)nc_mul9(d) << 8)
                   | ((uint32_t)nc_mul13(d) << 16)
                   | ((uint32_t)nc_mul11(d) << 24);
        g_td0[v] = t;
        g_td1[v] = nc_ror24(t);
        g_td2[v] = nc_ror16(t);
        g_td3[v] = nc_ror8(t);
    }
}

static const char *nc_backend_str(int id) {
    if (id == NC_BACKEND_X86_AESNI) return "x86-aesni";
    if (id == NC_BACKEND_ARM_CRYPTO) return "arm-crypto";
    return "soft";
}

#if defined(NC_X86)

static void nc_cpuid(unsigned leaf, unsigned sub, unsigned *a, unsigned *b, unsigned *c, unsigned *d) {
#if defined(_MSC_VER) && !defined(__clang__)
    int info[4];
    __cpuidex(info, (int)leaf, (int)sub);
    *a = (unsigned)info[0];
    *b = (unsigned)info[1];
    *c = (unsigned)info[2];
    *d = (unsigned)info[3];
#else
    *a = *b = *c = *d = 0;
    __cpuid_count(leaf, sub, *a, *b, *c, *d);
#endif
}

static void nc_detect(void) {
    unsigned a, b, c, d;
    unsigned max_leaf;
    nc_cpuid(0, 0, &a, &b, &c, &d);
    max_leaf = a;
    nc_cpuid(1, 0, &a, &b, &c, &d);
    g_caps.aes_ni = (c >> 25) & 1;
    g_caps.pclmulqdq = (c >> 1) & 1;
    g_caps.ssse3 = (c >> 9) & 1;
    g_caps.sse4_1 = (c >> 19) & 1;
    if (max_leaf >= 7) {
        nc_cpuid(7, 0, &a, &b, &c, &d);
        g_caps.avx2 = (b >> 5) & 1;
    }
    g_caps.arm_crypto = 0;
    g_backend = g_caps.aes_ni ? NC_BACKEND_X86_AESNI : NC_BACKEND_SOFT;
    {
        const char *env = getenv("NCRYPTO_BACKEND");
        if (env) {
            if (strcmp(env, "soft") == 0) g_backend = NC_BACKEND_SOFT;
            else if (strcmp(env, "aesni") == 0 && g_caps.aes_ni) g_backend = NC_BACKEND_X86_AESNI;
        }
    }
}

#else

static void nc_detect(void) {
    g_caps.aes_ni = 0;
    g_caps.pclmulqdq = 0;
    g_caps.ssse3 = 0;
    g_caps.sse4_1 = 0;
    g_caps.avx2 = 0;
    g_caps.arm_crypto = 0;
    g_backend = NC_BACKEND_SOFT;
}

#endif

int nc_init(void) {
    if (nc_state_load() == 2) return g_backend;
    if (nc_state_cas()) {
        nc_gen_tables();
        nc_detect();
        g_caps.backend_id = g_backend;
        g_caps.backend_name = nc_backend_str(g_backend);
        nc_state_done();
    } else {
        while (nc_state_load() != 2) {
        }
    }
    return g_backend;
}

static int nc_backend(void) {
    if (nc_state_load() != 2) nc_init();
    return g_backend;
}

int nc_backend_id(void) {
    return nc_backend();
}

const char *nc_backend_name(void) {
    nc_backend();
    return g_caps.backend_name;
}

void nc_get_caps(nc_caps_t *caps) {
    nc_backend();
    *caps = g_caps;
}

static void nc_soft_expand(nc_aes256_t *ctx, const uint8_t *key, int with_dec) {
    static const uint32_t rcon[7] = {0x01u, 0x02u, 0x04u, 0x08u, 0x10u, 0x20u, 0x40u};
    uint32_t *w = ctx->enc;
    uint32_t *dk = ctx->dec;
    for (unsigned i = 0; i < 8; i++) {
        w[i] = nc_ld32(key + 4 * i);
    }
    for (unsigned i = 8; i < 60; i++) {
        uint32_t t = w[i - 1];
        if ((i & 7) == 0) {
            t = nc_subw((t >> 8) | (t << 24)) ^ rcon[(i >> 3) - 1];
        } else if ((i & 7) == 4) {
            t = nc_subw(t);
        }
        w[i] = w[i - 8] ^ t;
    }
    if (with_dec) {
        for (unsigned j = 0; j < 4; j++) {
            dk[j] = w[56 + j];
            dk[56 + j] = w[j];
        }
        for (unsigned i = 1; i <= 13; i++) {
            const uint32_t *src = w + 4 * (14 - i);
            for (unsigned j = 0; j < 4; j++) {
                dk[4 * i + j] = nc_imcw(src[j]);
            }
        }
    }
}

static void nc_soft_enc_words(const uint32_t *rk, const uint32_t *in, uint32_t *out) {
    uint32_t s0 = in[0] ^ rk[0];
    uint32_t s1 = in[1] ^ rk[1];
    uint32_t s2 = in[2] ^ rk[2];
    uint32_t s3 = in[3] ^ rk[3];
    for (unsigned r = 1; r <= 13; r++) {
        const uint32_t *k = rk + 4 * r;
        uint32_t t0 = g_te0[s0 & 0xff] ^ g_te1[(s1 >> 8) & 0xff] ^ g_te2[(s2 >> 16) & 0xff] ^ g_te3[s3 >> 24] ^ k[0];
        uint32_t t1 = g_te0[s1 & 0xff] ^ g_te1[(s2 >> 8) & 0xff] ^ g_te2[(s3 >> 16) & 0xff] ^ g_te3[s0 >> 24] ^ k[1];
        uint32_t t2 = g_te0[s2 & 0xff] ^ g_te1[(s3 >> 8) & 0xff] ^ g_te2[(s0 >> 16) & 0xff] ^ g_te3[s1 >> 24] ^ k[2];
        uint32_t t3 = g_te0[s3 & 0xff] ^ g_te1[(s0 >> 8) & 0xff] ^ g_te2[(s1 >> 16) & 0xff] ^ g_te3[s2 >> 24] ^ k[3];
        s0 = t0;
        s1 = t1;
        s2 = t2;
        s3 = t3;
    }
    {
        const uint32_t *k = rk + 56;
        out[0] = ((uint32_t)g_sbox[s0 & 0xff]
                | ((uint32_t)g_sbox[(s1 >> 8) & 0xff] << 8)
                | ((uint32_t)g_sbox[(s2 >> 16) & 0xff] << 16)
                | ((uint32_t)g_sbox[s3 >> 24] << 24)) ^ k[0];
        out[1] = ((uint32_t)g_sbox[s1 & 0xff]
                | ((uint32_t)g_sbox[(s2 >> 8) & 0xff] << 8)
                | ((uint32_t)g_sbox[(s3 >> 16) & 0xff] << 16)
                | ((uint32_t)g_sbox[s0 >> 24] << 24)) ^ k[1];
        out[2] = ((uint32_t)g_sbox[s2 & 0xff]
                | ((uint32_t)g_sbox[(s3 >> 8) & 0xff] << 8)
                | ((uint32_t)g_sbox[(s0 >> 16) & 0xff] << 16)
                | ((uint32_t)g_sbox[s1 >> 24] << 24)) ^ k[2];
        out[3] = ((uint32_t)g_sbox[s3 & 0xff]
                | ((uint32_t)g_sbox[(s0 >> 8) & 0xff] << 8)
                | ((uint32_t)g_sbox[(s1 >> 16) & 0xff] << 16)
                | ((uint32_t)g_sbox[s2 >> 24] << 24)) ^ k[3];
    }
}

static void nc_soft_dec_words(const uint32_t *dk, const uint32_t *in, uint32_t *out) {
    uint32_t s0 = in[0] ^ dk[0];
    uint32_t s1 = in[1] ^ dk[1];
    uint32_t s2 = in[2] ^ dk[2];
    uint32_t s3 = in[3] ^ dk[3];
    for (unsigned r = 1; r <= 13; r++) {
        const uint32_t *k = dk + 4 * r;
        uint32_t t0 = g_td0[s0 & 0xff] ^ g_td1[(s3 >> 8) & 0xff] ^ g_td2[(s2 >> 16) & 0xff] ^ g_td3[s1 >> 24] ^ k[0];
        uint32_t t1 = g_td0[s1 & 0xff] ^ g_td1[(s0 >> 8) & 0xff] ^ g_td2[(s3 >> 16) & 0xff] ^ g_td3[s2 >> 24] ^ k[1];
        uint32_t t2 = g_td0[s2 & 0xff] ^ g_td1[(s1 >> 8) & 0xff] ^ g_td2[(s0 >> 16) & 0xff] ^ g_td3[s3 >> 24] ^ k[2];
        uint32_t t3 = g_td0[s3 & 0xff] ^ g_td1[(s2 >> 8) & 0xff] ^ g_td2[(s1 >> 16) & 0xff] ^ g_td3[s0 >> 24] ^ k[3];
        s0 = t0;
        s1 = t1;
        s2 = t2;
        s3 = t3;
    }
    {
        const uint32_t *k = dk + 56;
        out[0] = ((uint32_t)g_isbox[s0 & 0xff]
                | ((uint32_t)g_isbox[(s3 >> 8) & 0xff] << 8)
                | ((uint32_t)g_isbox[(s2 >> 16) & 0xff] << 16)
                | ((uint32_t)g_isbox[s1 >> 24] << 24)) ^ k[0];
        out[1] = ((uint32_t)g_isbox[s1 & 0xff]
                | ((uint32_t)g_isbox[(s0 >> 8) & 0xff] << 8)
                | ((uint32_t)g_isbox[(s3 >> 16) & 0xff] << 16)
                | ((uint32_t)g_isbox[s2 >> 24] << 24)) ^ k[1];
        out[2] = ((uint32_t)g_isbox[s2 & 0xff]
                | ((uint32_t)g_isbox[(s1 >> 8) & 0xff] << 8)
                | ((uint32_t)g_isbox[(s0 >> 16) & 0xff] << 16)
                | ((uint32_t)g_isbox[s3 >> 24] << 24)) ^ k[2];
        out[3] = ((uint32_t)g_isbox[s3 & 0xff]
                | ((uint32_t)g_isbox[(s2 >> 8) & 0xff] << 8)
                | ((uint32_t)g_isbox[(s1 >> 16) & 0xff] << 16)
                | ((uint32_t)g_isbox[s0 >> 24] << 24)) ^ k[3];
    }
}

static void nc_soft_enc_block(const nc_aes256_t *ctx, const uint8_t *in, uint8_t *out) {
    uint32_t s[4];
    s[0] = nc_ld32(in);
    s[1] = nc_ld32(in + 4);
    s[2] = nc_ld32(in + 8);
    s[3] = nc_ld32(in + 12);
    nc_soft_enc_words(ctx->enc, s, s);
    nc_st32(out, s[0]);
    nc_st32(out + 4, s[1]);
    nc_st32(out + 8, s[2]);
    nc_st32(out + 12, s[3]);
}

static void nc_soft_dec_block(const nc_aes256_t *ctx, const uint8_t *in, uint8_t *out) {
    uint32_t s[4];
    s[0] = nc_ld32(in);
    s[1] = nc_ld32(in + 4);
    s[2] = nc_ld32(in + 8);
    s[3] = nc_ld32(in + 12);
    nc_soft_dec_words(ctx->dec, s, s);
    nc_st32(out, s[0]);
    nc_st32(out + 4, s[1]);
    nc_st32(out + 8, s[2]);
    nc_st32(out + 12, s[3]);
}

static void nc_soft_ige_encrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                                 const uint8_t *iv, uint8_t *out) {
    uint32_t y[4], x[4], p[4], t[4], k[4];
    for (unsigned j = 0; j < 4; j++) {
        y[j] = nc_ld32(iv + 4 * j);
        x[j] = nc_ld32(iv + 16 + 4 * j);
    }
    while (len >= NC_BLOCK) {
        for (unsigned j = 0; j < 4; j++) {
            p[j] = nc_ld32(in + 4 * j);
            t[j] = p[j] ^ y[j];
        }
        nc_soft_enc_words(ctx->enc, t, k);
        for (unsigned j = 0; j < 4; j++) {
            t[j] = k[j] ^ x[j];
            y[j] = t[j];
            x[j] = p[j];
        }
        nc_st32(out, t[0]);
        nc_st32(out + 4, t[1]);
        nc_st32(out + 8, t[2]);
        nc_st32(out + 12, t[3]);
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
}

static void nc_soft_ige_decrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                                 const uint8_t *iv, uint8_t *out) {
    uint32_t pprev[4], cprev[4], c[4], t[4], k[4];
    for (unsigned j = 0; j < 4; j++) {
        pprev[j] = nc_ld32(iv + 16 + 4 * j);
        cprev[j] = nc_ld32(iv + 4 * j);
    }
    while (len >= NC_BLOCK) {
        for (unsigned j = 0; j < 4; j++) {
            c[j] = nc_ld32(in + 4 * j);
            t[j] = c[j] ^ pprev[j];
        }
        nc_soft_dec_words(ctx->dec, t, k);
        for (unsigned j = 0; j < 4; j++) {
            t[j] = k[j] ^ cprev[j];
            pprev[j] = t[j];
            cprev[j] = c[j];
        }
        nc_st32(out, t[0]);
        nc_st32(out + 4, t[1]);
        nc_st32(out + 8, t[2]);
        nc_st32(out + 12, t[3]);
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
}

static void nc_soft_cbc_encrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                                 const uint8_t *iv, uint8_t *out) {
    uint32_t c[4], p[4];
    for (unsigned j = 0; j < 4; j++) {
        c[j] = nc_ld32(iv + 4 * j);
    }
    while (len >= NC_BLOCK) {
        for (unsigned j = 0; j < 4; j++) {
            p[j] = nc_ld32(in + 4 * j) ^ c[j];
        }
        nc_soft_enc_words(ctx->enc, p, c);
        nc_st32(out, c[0]);
        nc_st32(out + 4, c[1]);
        nc_st32(out + 8, c[2]);
        nc_st32(out + 12, c[3]);
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
}

static void nc_soft_cbc_decrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                                 const uint8_t *iv, uint8_t *out) {
    uint32_t cprev[4], c[4], t[4];
    for (unsigned j = 0; j < 4; j++) {
        cprev[j] = nc_ld32(iv + 4 * j);
    }
    while (len >= NC_BLOCK) {
        for (unsigned j = 0; j < 4; j++) {
            c[j] = nc_ld32(in + 4 * j);
            t[j] = c[j];
        }
        nc_soft_dec_words(ctx->dec, t, t);
        for (unsigned j = 0; j < 4; j++) {
            t[j] ^= cprev[j];
            cprev[j] = c[j];
        }
        nc_st32(out, t[0]);
        nc_st32(out + 4, t[1]);
        nc_st32(out + 8, t[2]);
        nc_st32(out + 12, t[3]);
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
}

static void nc_soft_ctr_xor(const nc_aes256_t *ctx, nc_ctr_t *st,
                             const uint8_t *in, size_t len, uint8_t *out) {
    if (len == 0) return;
    if (st->state < 16) {
        size_t k = (size_t)(16 - st->state);
        if (k > len) k = len;
        const uint8_t *ks = st->ks + st->state;
        for (size_t j = 0; j < k; j++) {
            out[j] = in[j] ^ ks[j];
        }
        st->state = (uint8_t)(st->state + (unsigned)k);
        st->offset += k;
        in += k;
        out += k;
        len -= k;
        if (len == 0) return;
    }
    while (len >= NC_BLOCK) {
        uint32_t cw[4], kw[4];
        for (unsigned j = 0; j < 4; j++) {
            cw[j] = nc_ld32(st->iv + 4 * j);
        }
        nc_soft_enc_words(ctx->enc, cw, kw);
        for (unsigned j = 0; j < 4; j++) {
            nc_st32(out + 4 * j, nc_ld32(in + 4 * j) ^ kw[j]);
        }
        nc_be_inc(st->iv);
        st->offset += NC_BLOCK;
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
    if (len) {
        uint32_t cw[4], kw[4];
        for (unsigned j = 0; j < 4; j++) {
            cw[j] = nc_ld32(st->iv + 4 * j);
        }
        nc_soft_enc_words(ctx->enc, cw, kw);
        for (unsigned j = 0; j < 4; j++) {
            nc_st32(st->ks + 4 * j, kw[j]);
        }
        for (size_t j = 0; j < len; j++) {
            out[j] = in[j] ^ st->ks[j];
        }
        st->state = (uint8_t)len;
        st->offset += len;
        nc_be_inc(st->iv);
    }
}

#if defined(NC_HAS_AESNI)

static NC_AESNI_ATTR inline __m128i nc_ld128(const uint32_t *p) {
    return _mm_loadu_si128((const __m128i *)(const void *)p);
}

static NC_AESNI_ATTR inline void nc_st128(uint32_t *p, __m128i v) {
    _mm_storeu_si128((__m128i *)(void *)p, v);
}

static NC_AESNI_ATTR inline __m128i nc_ldb(const uint8_t *p) {
    return _mm_loadu_si128((const __m128i *)(const void *)p);
}

static NC_AESNI_ATTR inline void nc_stb(uint8_t *p, __m128i v) {
    _mm_storeu_si128((__m128i *)(void *)p, v);
}

static NC_AESNI_ATTR __m128i nc_aesni_enc(const uint32_t *rk, __m128i v) {
    v = _mm_xor_si128(v, nc_ld128(rk));
    for (unsigned r = 1; r <= 13; r++) {
        v = _mm_aesenc_si128(v, nc_ld128(rk + 4 * r));
    }
    return _mm_aesenclast_si128(v, nc_ld128(rk + 56));
}

static NC_AESNI_ATTR __m128i nc_aesni_dec(const uint32_t *dk, __m128i v) {
    v = _mm_xor_si128(v, nc_ld128(dk));
    for (unsigned r = 1; r <= 13; r++) {
        v = _mm_aesdec_si128(v, nc_ld128(dk + 4 * r));
    }
    return _mm_aesdeclast_si128(v, nc_ld128(dk + 56));
}

#define NC_KS_STEP(RC, O1, O2) \
    t = _mm_shuffle_epi32(_mm_aeskeygenassist_si128(t2, RC), 0xff); \
    t1 = _mm_xor_si128(t1, _mm_slli_si128(t1, 4)); \
    t1 = _mm_xor_si128(t1, _mm_slli_si128(t1, 8)); \
    t1 = _mm_xor_si128(t1, t); \
    nc_st128(ctx->enc + O1, t1); \
    t = _mm_shuffle_epi32(_mm_aeskeygenassist_si128(t1, 0), 0xaa); \
    t2 = _mm_xor_si128(t2, _mm_slli_si128(t2, 4)); \
    t2 = _mm_xor_si128(t2, _mm_slli_si128(t2, 8)); \
    t2 = _mm_xor_si128(t2, t); \
    nc_st128(ctx->enc + O2, t2)

static NC_AESNI_ATTR void nc_aesni_expand(nc_aes256_t *ctx, const uint8_t *key, int with_dec) {
    __m128i t1 = nc_ldb(key);
    __m128i t2 = nc_ldb(key + 16);
    __m128i t;
    nc_st128(ctx->enc, t1);
    nc_st128(ctx->enc + 4, t2);

    NC_KS_STEP(0x01, 8, 12);
    NC_KS_STEP(0x02, 16, 20);
    NC_KS_STEP(0x04, 24, 28);
    NC_KS_STEP(0x08, 32, 36);
    NC_KS_STEP(0x10, 40, 44);
    NC_KS_STEP(0x20, 48, 52);

#undef NC_KS_STEP

    t = _mm_shuffle_epi32(_mm_aeskeygenassist_si128(t2, 0x40), 0xff);
    t1 = _mm_xor_si128(t1, _mm_slli_si128(t1, 4));
    t1 = _mm_xor_si128(t1, _mm_slli_si128(t1, 8));
    t1 = _mm_xor_si128(t1, t);
    nc_st128(ctx->enc + 56, t1);

    if (with_dec) {
        nc_st128(ctx->dec, nc_ld128(ctx->enc + 56));
        nc_st128(ctx->dec + 56, nc_ld128(ctx->enc));
        for (unsigned i = 1; i <= 13; i++) {
            nc_st128(ctx->dec + 4 * i, _mm_aesimc_si128(nc_ld128(ctx->enc + 4 * (14 - i))));
        }
    }
}

static NC_AESNI_ATTR void nc_aesni_ige_encrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                                                 const uint8_t *iv, uint8_t *out) {
    __m128i y = nc_ldb(iv);
    __m128i x = nc_ldb(iv + 16);
    while (len >= NC_BLOCK) {
        __m128i p = nc_ldb(in);
        __m128i c = _mm_xor_si128(nc_aesni_enc(ctx->enc, _mm_xor_si128(p, y)), x);
        nc_stb(out, c);
        x = p;
        y = c;
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
}

static NC_AESNI_ATTR void nc_aesni_ige_decrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                                                 const uint8_t *iv, uint8_t *out) {
    __m128i pprev = nc_ldb(iv + 16);
    __m128i cprev = nc_ldb(iv);
    while (len >= NC_BLOCK) {
        __m128i c = nc_ldb(in);
        __m128i p = _mm_xor_si128(nc_aesni_dec(ctx->dec, _mm_xor_si128(c, pprev)), cprev);
        nc_stb(out, p);
        pprev = p;
        cprev = c;
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
}

static NC_AESNI_ATTR void nc_aesni_cbc_encrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                                                 const uint8_t *iv, uint8_t *out) {
    __m128i c = nc_ldb(iv);
    while (len >= NC_BLOCK) {
        c = nc_aesni_enc(ctx->enc, _mm_xor_si128(nc_ldb(in), c));
        nc_stb(out, c);
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
}

static NC_AESNI_ATTR void nc_aesni_cbc_decrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                                                 const uint8_t *iv, uint8_t *out) {
    __m128i cprev = nc_ldb(iv);
    while (len >= NC_BLOCK) {
        __m128i c = nc_ldb(in);
        nc_stb(out, _mm_xor_si128(nc_aesni_dec(ctx->dec, c), cprev));
        cprev = c;
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
}

static NC_AESNI_ATTR void nc_aesni_ctr_xor(const nc_aes256_t *ctx, nc_ctr_t *st,
                                             const uint8_t *in, size_t len, uint8_t *out) {
    const uint32_t *rk = ctx->enc;
    if (len == 0) return;
    if (st->state < 16) {
        size_t k = (size_t)(16 - st->state);
        if (k > len) k = len;
        const uint8_t *ks = st->ks + st->state;
        for (size_t j = 0; j < k; j++) {
            out[j] = in[j] ^ ks[j];
        }
        st->state = (uint8_t)(st->state + (unsigned)k);
        st->offset += k;
        in += k;
        out += k;
        len -= k;
        if (len == 0) return;
    }
    while (len >= 128) {
        uint8_t cb[128];
        __m128i k0, k1, k2, k3, k4, k5, k6, k7;
        memcpy(cb, st->iv, 16);
        for (unsigned b = 1; b < 8; b++) {
            memcpy(cb + 16 * b, cb + 16 * (b - 1), 16);
            nc_be_inc(cb + 16 * b);
        }
        k0 = nc_aesni_enc(rk, nc_ldb(cb));
        k1 = nc_aesni_enc(rk, nc_ldb(cb + 16));
        k2 = nc_aesni_enc(rk, nc_ldb(cb + 32));
        k3 = nc_aesni_enc(rk, nc_ldb(cb + 48));
        k4 = nc_aesni_enc(rk, nc_ldb(cb + 64));
        k5 = nc_aesni_enc(rk, nc_ldb(cb + 80));
        k6 = nc_aesni_enc(rk, nc_ldb(cb + 96));
        k7 = nc_aesni_enc(rk, nc_ldb(cb + 112));
        nc_stb(out, _mm_xor_si128(nc_ldb(in), k0));
        nc_stb(out + 16, _mm_xor_si128(nc_ldb(in + 16), k1));
        nc_stb(out + 32, _mm_xor_si128(nc_ldb(in + 32), k2));
        nc_stb(out + 48, _mm_xor_si128(nc_ldb(in + 48), k3));
        nc_stb(out + 64, _mm_xor_si128(nc_ldb(in + 64), k4));
        nc_stb(out + 80, _mm_xor_si128(nc_ldb(in + 80), k5));
        nc_stb(out + 96, _mm_xor_si128(nc_ldb(in + 96), k6));
        nc_stb(out + 112, _mm_xor_si128(nc_ldb(in + 112), k7));
        memcpy(st->iv, cb + 112, 16);
        nc_be_inc(st->iv);
        st->offset += 128;
        in += 128;
        out += 128;
        len -= 128;
    }
    while (len >= NC_BLOCK) {
        nc_stb(out, _mm_xor_si128(nc_ldb(in), nc_aesni_enc(rk, nc_ldb(st->iv))));
        nc_be_inc(st->iv);
        st->offset += NC_BLOCK;
        in += NC_BLOCK;
        out += NC_BLOCK;
        len -= NC_BLOCK;
    }
    if (len) {
        nc_stb(st->ks, nc_aesni_enc(rk, nc_ldb(st->iv)));
        for (size_t j = 0; j < len; j++) {
            out[j] = in[j] ^ st->ks[j];
        }
        st->state = (uint8_t)len;
        st->offset += len;
        nc_be_inc(st->iv);
    }
}

#endif

void nc_aes256_init_enc(nc_aes256_t *ctx, const uint8_t key[NC_KEY_LEN]) {
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_aesni_expand(ctx, key, 0);
        return;
    }
#endif
    nc_soft_expand(ctx, key, 0);
}

void nc_aes256_init(nc_aes256_t *ctx, const uint8_t key[NC_KEY_LEN]) {
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_aesni_expand(ctx, key, 1);
        return;
    }
#endif
    nc_soft_expand(ctx, key, 1);
}

void nc_aes256_encrypt_block(const nc_aes256_t *ctx,
                              const uint8_t in[NC_BLOCK], uint8_t out[NC_BLOCK]) {
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_stb(out, nc_aesni_enc(ctx->enc, nc_ldb(in)));
        return;
    }
#endif
    nc_soft_enc_block(ctx, in, out);
}

void nc_aes256_decrypt_block(const nc_aes256_t *ctx,
                              const uint8_t in[NC_BLOCK], uint8_t out[NC_BLOCK]) {
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_stb(out, nc_aesni_dec(ctx->dec, nc_ldb(in)));
        return;
    }
#endif
    nc_soft_dec_block(ctx, in, out);
}

void nc_ige256_encrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                        const uint8_t iv[NC_IGE_IV_LEN], uint8_t *out) {
    if (len < NC_BLOCK) return;
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_aesni_ige_encrypt(ctx, in, len, iv, out);
        return;
    }
#endif
    nc_soft_ige_encrypt(ctx, in, len, iv, out);
}

void nc_ige256_decrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                        const uint8_t iv[NC_IGE_IV_LEN], uint8_t *out) {
    if (len < NC_BLOCK) return;
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_aesni_ige_decrypt(ctx, in, len, iv, out);
        return;
    }
#endif
    nc_soft_ige_decrypt(ctx, in, len, iv, out);
}

void nc_cbc256_encrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                        const uint8_t iv[NC_CBC_IV_LEN], uint8_t *out) {
    if (len < NC_BLOCK) return;
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_aesni_cbc_encrypt(ctx, in, len, iv, out);
        return;
    }
#endif
    nc_soft_cbc_encrypt(ctx, in, len, iv, out);
}

void nc_cbc256_decrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                        const uint8_t iv[NC_CBC_IV_LEN], uint8_t *out) {
    if (len < NC_BLOCK) return;
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_aesni_cbc_decrypt(ctx, in, len, iv, out);
        return;
    }
#endif
    nc_soft_cbc_decrypt(ctx, in, len, iv, out);
}

void nc_ctr_init(const nc_aes256_t *ctx, nc_ctr_t *st,
                  const uint8_t iv[NC_CTR_IV_LEN], uint8_t state) {
    memcpy(st->base, iv, 16);
    memcpy(st->iv, iv, 16);
    st->offset = 0;
    st->state = 16;
    if (state > 0 && state < 16) {
        nc_aes256_encrypt_block(ctx, st->iv, st->ks);
        st->state = state;
        st->offset = state;
        nc_be_inc(st->iv);
    }
}

void nc_ctr_xor(const nc_aes256_t *ctx, nc_ctr_t *st,
                 const uint8_t *in, size_t len, uint8_t *out) {
    if (len == 0) return;
#if defined(NC_HAS_AESNI)
    if (nc_backend() == NC_BACKEND_X86_AESNI) {
        nc_aesni_ctr_xor(ctx, st, in, len, out);
        return;
    }
#endif
    nc_soft_ctr_xor(ctx, st, in, len, out);
}

void nc_ctr_seek(const nc_aes256_t *ctx, nc_ctr_t *st, uint64_t pos) {
    memcpy(st->iv, st->base, 16);
    st->offset = pos;
    if (pos >> 4) {
        nc_be_add(st->iv, pos >> 4);
    }
    if (pos & 15) {
        nc_aes256_encrypt_block(ctx, st->iv, st->ks);
        st->state = (uint8_t)(pos & 15);
        nc_be_inc(st->iv);
    } else {
        st->state = 16;
    }
}
