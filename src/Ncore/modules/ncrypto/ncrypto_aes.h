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

#ifndef NCRYPTO_AES_H
#define NCRYPTO_AES_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NC_BLOCK       16
#define NC_KEY_LEN     32
#define NC_IGE_IV_LEN  32
#define NC_CBC_IV_LEN  16
#define NC_CTR_IV_LEN  16

#define NC_BACKEND_SOFT       0
#define NC_BACKEND_X86_AESNI  1
#define NC_BACKEND_ARM_CRYPTO 2

#if defined(_MSC_VER) && !defined(__clang__)
#  define NC_ALIGN16 __declspec(align(16))
#else
#  define NC_ALIGN16 __attribute__((aligned(16)))
#endif

typedef struct {
    NC_ALIGN16 uint32_t enc[60];
    NC_ALIGN16 uint32_t dec[60];
} nc_aes256_t;

typedef struct {
    uint8_t  base[16];
    uint8_t  iv[16];
    uint8_t  ks[16];
    uint8_t  state;
    uint64_t offset;
} nc_ctr_t;

typedef struct {
    int aes_ni;
    int pclmulqdq;
    int ssse3;
    int sse4_1;
    int avx2;
    int arm_crypto;
    int backend_id;
    const char *backend_name;
} nc_caps_t;

int nc_init(void);
int nc_backend_id(void);
const char *nc_backend_name(void);
void nc_get_caps(nc_caps_t *caps);

void nc_aes256_init_enc(nc_aes256_t *ctx, const uint8_t key[NC_KEY_LEN]);
void nc_aes256_init(nc_aes256_t *ctx, const uint8_t key[NC_KEY_LEN]);
void nc_aes256_encrypt_block(const nc_aes256_t *ctx,
                              const uint8_t in[NC_BLOCK], uint8_t out[NC_BLOCK]);
void nc_aes256_decrypt_block(const nc_aes256_t *ctx,
                              const uint8_t in[NC_BLOCK], uint8_t out[NC_BLOCK]);

void nc_ige256_encrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                        const uint8_t iv[NC_IGE_IV_LEN], uint8_t *out);
void nc_ige256_decrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                        const uint8_t iv[NC_IGE_IV_LEN], uint8_t *out);
void nc_cbc256_encrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                        const uint8_t iv[NC_CBC_IV_LEN], uint8_t *out);
void nc_cbc256_decrypt(const nc_aes256_t *ctx, const uint8_t *in, size_t len,
                        const uint8_t iv[NC_CBC_IV_LEN], uint8_t *out);

void nc_ctr_init(const nc_aes256_t *ctx, nc_ctr_t *st,
                  const uint8_t iv[NC_CTR_IV_LEN], uint8_t state);
void nc_ctr_xor(const nc_aes256_t *ctx, nc_ctr_t *st,
                 const uint8_t *in, size_t len, uint8_t *out);
void nc_ctr_seek(const nc_aes256_t *ctx, nc_ctr_t *st, uint64_t pos);

#ifdef __cplusplus
}
#endif

#endif
