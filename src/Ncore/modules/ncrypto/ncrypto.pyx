# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: initializedcheck=False
# cython: nonecheck=False
# cython: freethreading_compatible=True

# Copyright 2026 zovdev
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from libc.stdint cimport uint8_t, uint32_t, uint64_t
from libc.stddef cimport size_t

cdef extern from "Python.h":
    ctypedef struct Py_buffer:
        void* buf
        Py_ssize_t len
        int readonly
        void* obj

    int PyBUF_SIMPLE
    int PyBUF_WRITABLE

    int PyObject_GetBuffer(object obj, Py_buffer* view, int flags)
    void PyBuffer_Release(Py_buffer* view)
    bytes PyBytes_FromStringAndSize(const char* s, Py_ssize_t n)
    char* PyBytes_AS_STRING(object s)
    Py_ssize_t PyBytes_GET_SIZE(object s)
    char* PyByteArray_AS_STRING(object s)
    Py_ssize_t PyByteArray_GET_SIZE(object s)

cdef extern from "ncrypto_aes.h" nogil:
    enum:
        NC_BLOCK
        NC_KEY_LEN
        NC_IGE_IV_LEN
        NC_CBC_IV_LEN
        NC_CTR_IV_LEN
        NC_BACKEND_SOFT
        NC_BACKEND_X86_AESNI
        NC_BACKEND_ARM_CRYPTO

    ctypedef struct nc_aes256_t:
        uint32_t enc[60]
        uint32_t dec[60]

    ctypedef struct nc_ctr_t:
        uint8_t base[16]
        uint8_t iv[16]
        uint8_t ks[16]
        uint8_t state
        uint64_t offset

    ctypedef struct nc_caps_t:
        int aes_ni
        int pclmulqdq
        int ssse3
        int sse4_1
        int avx2
        int arm_crypto
        int backend_id
        const char* backend_name

    int nc_init()
    int nc_backend_id()
    const char* nc_backend_name()
    void nc_get_caps(nc_caps_t* caps)
    void nc_aes256_init_enc(nc_aes256_t* ctx, const unsigned char* key)
    void nc_aes256_init(nc_aes256_t* ctx, const unsigned char* key)
    void nc_ige256_encrypt(const nc_aes256_t* ctx, const unsigned char* data, size_t len, const unsigned char* iv, unsigned char* out)
    void nc_ige256_decrypt(const nc_aes256_t* ctx, const unsigned char* data, size_t len, const unsigned char* iv, unsigned char* out)
    void nc_cbc256_encrypt(const nc_aes256_t* ctx, const unsigned char* data, size_t len, const unsigned char* iv, unsigned char* out)
    void nc_cbc256_decrypt(const nc_aes256_t* ctx, const unsigned char* data, size_t len, const unsigned char* iv, unsigned char* out)
    void nc_ctr_init(const nc_aes256_t* ctx, nc_ctr_t* st, const unsigned char* iv, uint8_t state)
    void nc_ctr_xor(const nc_aes256_t* ctx, nc_ctr_t* st, const unsigned char* data, size_t len, unsigned char* out)
    void nc_ctr_seek(const nc_aes256_t* ctx, nc_ctr_t* st, uint64_t pos)


nc_init()


cdef inline void _release(Py_buffer* view):
    if view.obj != NULL:
        PyBuffer_Release(view)
        view.obj = NULL


cdef inline const unsigned char* _readonly(object data, Py_buffer* view, Py_ssize_t* length) except NULL:
    if type(data) is bytes:
        view.obj = NULL
        length[0] = PyBytes_GET_SIZE(data)
        return <const unsigned char*> PyBytes_AS_STRING(data)
    if type(data) is bytearray:
        view.obj = NULL
        length[0] = PyByteArray_GET_SIZE(data)
        return <const unsigned char*> PyByteArray_AS_STRING(data)
    if PyObject_GetBuffer(data, view, PyBUF_SIMPLE) != 0:
        return NULL
    length[0] = view.len
    return <const unsigned char*> view.buf


cdef inline unsigned char* _writable(object data, Py_buffer* view, Py_ssize_t* length) except NULL:
    if type(data) is bytearray:
        view.obj = NULL
        length[0] = PyByteArray_GET_SIZE(data)
        return <unsigned char*> PyByteArray_AS_STRING(data)
    if PyObject_GetBuffer(data, view, PyBUF_SIMPLE | PyBUF_WRITABLE) != 0:
        return NULL
    length[0] = view.len
    return <unsigned char*> view.buf


cdef class AesIge256:
    cdef nc_aes256_t ctx

    def __cinit__(self, key):
        cdef Py_buffer kview
        cdef const unsigned char* kp
        cdef Py_ssize_t klen
        kview.obj = NULL
        try:
            kp = _readonly(key, &kview, &klen)
            if klen != NC_KEY_LEN:
                raise ValueError("ige256 key must be 32 bytes")
            with nogil:
                nc_aes256_init(&self.ctx, kp)
        finally:
            _release(&kview)

    def encrypt(self, data, iv):
        cdef Py_buffer dview
        cdef Py_buffer iview
        cdef const unsigned char* dp
        cdef const unsigned char* vp
        cdef Py_ssize_t dn
        cdef Py_ssize_t vn
        cdef bytes result
        cdef unsigned char* rp
        dview.obj = NULL
        iview.obj = NULL
        try:
            dp = _readonly(data, &dview, &dn)
            vp = _readonly(iv, &iview, &vn)
            if vn != NC_IGE_IV_LEN:
                raise ValueError("ige256 iv must be 32 bytes")
            if dn == 0:
                return b""
            if dn % NC_BLOCK != 0:
                raise ValueError("ige256 data length must be a multiple of 16")
            result = PyBytes_FromStringAndSize(NULL, dn)
            rp = <unsigned char*> PyBytes_AS_STRING(result)
            with nogil:
                nc_ige256_encrypt(&self.ctx, dp, <size_t>dn, vp, rp)
            return result
        finally:
            _release(&dview)
            _release(&iview)

    def decrypt(self, data, iv):
        cdef Py_buffer dview
        cdef Py_buffer iview
        cdef const unsigned char* dp
        cdef const unsigned char* vp
        cdef Py_ssize_t dn
        cdef Py_ssize_t vn
        cdef bytes result
        cdef unsigned char* rp
        dview.obj = NULL
        iview.obj = NULL
        try:
            dp = _readonly(data, &dview, &dn)
            vp = _readonly(iv, &iview, &vn)
            if vn != NC_IGE_IV_LEN:
                raise ValueError("ige256 iv must be 32 bytes")
            if dn == 0:
                return b""
            if dn % NC_BLOCK != 0:
                raise ValueError("ige256 data length must be a multiple of 16")
            result = PyBytes_FromStringAndSize(NULL, dn)
            rp = <unsigned char*> PyBytes_AS_STRING(result)
            with nogil:
                nc_ige256_decrypt(&self.ctx, dp, <size_t>dn, vp, rp)
            return result
        finally:
            _release(&dview)
            _release(&iview)

    def encrypt_into(self, data, iv):
        cdef Py_buffer dview
        cdef Py_buffer iview
        cdef unsigned char* dp
        cdef const unsigned char* vp
        cdef Py_ssize_t dn
        cdef Py_ssize_t vn
        dview.obj = NULL
        iview.obj = NULL
        try:
            dp = _writable(data, &dview, &dn)
            vp = _readonly(iv, &iview, &vn)
            if vn != NC_IGE_IV_LEN:
                raise ValueError("ige256 iv must be 32 bytes")
            if dn == 0:
                return
            if dn % NC_BLOCK != 0:
                raise ValueError("ige256 data length must be a multiple of 16")
            with nogil:
                nc_ige256_encrypt(&self.ctx, dp, <size_t>dn, vp, dp)
        finally:
            _release(&dview)
            _release(&iview)

    def decrypt_into(self, data, iv):
        cdef Py_buffer dview
        cdef Py_buffer iview
        cdef unsigned char* dp
        cdef const unsigned char* vp
        cdef Py_ssize_t dn
        cdef Py_ssize_t vn
        dview.obj = NULL
        iview.obj = NULL
        try:
            dp = _writable(data, &dview, &dn)
            vp = _readonly(iv, &iview, &vn)
            if vn != NC_IGE_IV_LEN:
                raise ValueError("ige256 iv must be 32 bytes")
            if dn == 0:
                return
            if dn % NC_BLOCK != 0:
                raise ValueError("ige256 data length must be a multiple of 16")
            with nogil:
                nc_ige256_decrypt(&self.ctx, dp, <size_t>dn, vp, dp)
        finally:
            _release(&dview)
            _release(&iview)


cdef class AesCbc256:
    cdef nc_aes256_t ctx

    def __cinit__(self, key):
        cdef Py_buffer kview
        cdef const unsigned char* kp
        cdef Py_ssize_t klen
        kview.obj = NULL
        try:
            kp = _readonly(key, &kview, &klen)
            if klen != NC_KEY_LEN:
                raise ValueError("cbc256 key must be 32 bytes")
            with nogil:
                nc_aes256_init(&self.ctx, kp)
        finally:
            _release(&kview)

    def encrypt(self, data, iv):
        cdef Py_buffer dview
        cdef Py_buffer iview
        cdef const unsigned char* dp
        cdef const unsigned char* vp
        cdef Py_ssize_t dn
        cdef Py_ssize_t vn
        cdef bytes result
        cdef unsigned char* rp
        dview.obj = NULL
        iview.obj = NULL
        try:
            dp = _readonly(data, &dview, &dn)
            vp = _readonly(iv, &iview, &vn)
            if vn != NC_CBC_IV_LEN:
                raise ValueError("cbc256 iv must be 16 bytes")
            if dn == 0:
                return b""
            if dn % NC_BLOCK != 0:
                raise ValueError("cbc256 data length must be a multiple of 16")
            result = PyBytes_FromStringAndSize(NULL, dn)
            rp = <unsigned char*> PyBytes_AS_STRING(result)
            with nogil:
                nc_cbc256_encrypt(&self.ctx, dp, <size_t>dn, vp, rp)
            return result
        finally:
            _release(&dview)
            _release(&iview)

    def decrypt(self, data, iv):
        cdef Py_buffer dview
        cdef Py_buffer iview
        cdef const unsigned char* dp
        cdef const unsigned char* vp
        cdef Py_ssize_t dn
        cdef Py_ssize_t vn
        cdef bytes result
        cdef unsigned char* rp
        dview.obj = NULL
        iview.obj = NULL
        try:
            dp = _readonly(data, &dview, &dn)
            vp = _readonly(iv, &iview, &vn)
            if vn != NC_CBC_IV_LEN:
                raise ValueError("cbc256 iv must be 16 bytes")
            if dn == 0:
                return b""
            if dn % NC_BLOCK != 0:
                raise ValueError("cbc256 data length must be a multiple of 16")
            result = PyBytes_FromStringAndSize(NULL, dn)
            rp = <unsigned char*> PyBytes_AS_STRING(result)
            with nogil:
                nc_cbc256_decrypt(&self.ctx, dp, <size_t>dn, vp, rp)
            return result
        finally:
            _release(&dview)
            _release(&iview)

    def encrypt_into(self, data, iv):
        cdef Py_buffer dview
        cdef Py_buffer iview
        cdef unsigned char* dp
        cdef const unsigned char* vp
        cdef Py_ssize_t dn
        cdef Py_ssize_t vn
        dview.obj = NULL
        iview.obj = NULL
        try:
            dp = _writable(data, &dview, &dn)
            vp = _readonly(iv, &iview, &vn)
            if vn != NC_CBC_IV_LEN:
                raise ValueError("cbc256 iv must be 16 bytes")
            if dn == 0:
                return
            if dn % NC_BLOCK != 0:
                raise ValueError("cbc256 data length must be a multiple of 16")
            with nogil:
                nc_cbc256_encrypt(&self.ctx, dp, <size_t>dn, vp, dp)
        finally:
            _release(&dview)
            _release(&iview)

    def decrypt_into(self, data, iv):
        cdef Py_buffer dview
        cdef Py_buffer iview
        cdef unsigned char* dp
        cdef const unsigned char* vp
        cdef Py_ssize_t dn
        cdef Py_ssize_t vn
        dview.obj = NULL
        iview.obj = NULL
        try:
            dp = _writable(data, &dview, &dn)
            vp = _readonly(iv, &iview, &vn)
            if vn != NC_CBC_IV_LEN:
                raise ValueError("cbc256 iv must be 16 bytes")
            if dn == 0:
                return
            if dn % NC_BLOCK != 0:
                raise ValueError("cbc256 data length must be a multiple of 16")
            with nogil:
                nc_cbc256_decrypt(&self.ctx, dp, <size_t>dn, vp, dp)
        finally:
            _release(&dview)
            _release(&iview)


cdef class AesCtr256:
    cdef nc_aes256_t ctx
    cdef nc_ctr_t st

    def __cinit__(self, key, iv, state=0):
        cdef Py_buffer kview
        cdef Py_buffer iview
        cdef const unsigned char* kp
        cdef const unsigned char* vp
        cdef Py_ssize_t klen
        cdef Py_ssize_t vlen
        cdef Py_ssize_t s
        kview.obj = NULL
        iview.obj = NULL
        try:
            kp = _readonly(key, &kview, &klen)
            vp = _readonly(iv, &iview, &vlen)
            if klen != NC_KEY_LEN:
                raise ValueError("ctr256 key must be 32 bytes")
            if vlen != NC_CTR_IV_LEN:
                raise ValueError("ctr256 iv must be 16 bytes")
            s = state
            if s < 0 or s > 15:
                raise ValueError("ctr256 state must be within 0..15")
            with nogil:
                nc_aes256_init_enc(&self.ctx, kp)
                nc_ctr_init(&self.ctx, &self.st, vp, <uint8_t>s)
        finally:
            _release(&kview)
            _release(&iview)

    def crypt(self, data):
        cdef Py_buffer dview
        cdef const unsigned char* dp
        cdef Py_ssize_t dn
        cdef bytes result
        cdef unsigned char* rp
        dview.obj = NULL
        try:
            dp = _readonly(data, &dview, &dn)
            if dn == 0:
                return b""
            result = PyBytes_FromStringAndSize(NULL, dn)
            rp = <unsigned char*> PyBytes_AS_STRING(result)
            with nogil:
                nc_ctr_xor(&self.ctx, &self.st, dp, <size_t>dn, rp)
            return result
        finally:
            _release(&dview)

    def crypt_into(self, data):
        cdef Py_buffer dview
        cdef unsigned char* dp
        cdef Py_ssize_t dn
        dview.obj = NULL
        try:
            dp = _writable(data, &dview, &dn)
            if dn == 0:
                return
            with nogil:
                nc_ctr_xor(&self.ctx, &self.st, dp, <size_t>dn, dp)
        finally:
            _release(&dview)

    def seek(self, Py_ssize_t pos):
        if pos < 0:
            raise ValueError("ctr256 seek position must be non-negative")
        with nogil:
            nc_ctr_seek(&self.ctx, &self.st, <uint64_t>pos)

    @property
    def offset(self):
        return self.st.offset

    @property
    def state(self):
        return self.st.state


def features():
    cdef nc_caps_t caps
    nc_get_caps(&caps)
    return {
        "aes_ni": caps.aes_ni,
        "pclmulqdq": caps.pclmulqdq,
        "ssse3": caps.ssse3,
        "sse4_1": caps.sse4_1,
        "avx2": caps.avx2,
        "arm_crypto": caps.arm_crypto,
        "backend_id": caps.backend_id,
        "backend": caps.backend_name.decode("utf-8"),
    }


def backend():
    return nc_backend_name().decode("utf-8")


def backend_id():
    return nc_backend_id()
