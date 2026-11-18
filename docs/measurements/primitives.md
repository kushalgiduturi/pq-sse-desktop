# Primitive timings

Measured with `python -m pqsse.bench_primitives` on Intel64 Family 6 Model 186 Stepping 2, GenuineIntel, Windows 10, Python 3.11.9, cryptography 50.0.2. Median of the runs shown, after one warm-up, in microseconds; 64-byte message. Numbers from one computer: they show the ratio between backends, not a promise.

| Family | Algorithm | Operation | Backend | Median (us) | Runs |
| --- | --- | --- | --- | ---: | ---: |
| KEM | ML-KEM-512 | keygen | pure | 1,814.4 | 15 |
| KEM | ML-KEM-512 | encapsulate | pure | 2,706.0 | 15 |
| KEM | ML-KEM-512 | decapsulate | pure | 3,820.4 | 15 |
| KEM | ML-KEM-768 | keygen | pure | 3,270.1 | 15 |
| KEM | ML-KEM-768 | encapsulate | pure | 4,093.2 | 15 |
| KEM | ML-KEM-768 | decapsulate | pure | 6,896.0 | 15 |
| KEM | ML-KEM-1024 | keygen | pure | 4,759.3 | 15 |
| KEM | ML-KEM-1024 | encapsulate | pure | 5,781.7 | 15 |
| KEM | ML-KEM-1024 | decapsulate | pure | 8,234.8 | 15 |
| SIG | ML-DSA-44 | keygen | pure | 6,324.7 | 15 |
| SIG | ML-DSA-44 | sign | pure | 27,700.7 | 15 |
| SIG | ML-DSA-44 | verify | pure | 7,087.4 | 15 |
| SIG | ML-DSA-65 | keygen | pure | 9,622.6 | 15 |
| SIG | ML-DSA-65 | sign | pure | 44,079.7 | 15 |
| SIG | ML-DSA-65 | verify | pure | 13,299.6 | 15 |
| SIG | ML-DSA-87 | keygen | pure | 14,894.3 | 15 |
| SIG | ML-DSA-87 | sign | pure | 69,478.8 | 15 |
| SIG | ML-DSA-87 | verify | pure | 16,679.0 | 15 |
| KEM | ML-KEM-768 | keygen | native | 186.5 | 500 |
| KEM | ML-KEM-768 | encapsulate | native | 60.5 | 500 |
| KEM | ML-KEM-768 | decapsulate | native | 220.1 | 500 |
| KEM | ML-KEM-1024 | keygen | native | 261.9 | 500 |
| KEM | ML-KEM-1024 | encapsulate | native | 83.6 | 500 |
| KEM | ML-KEM-1024 | decapsulate | native | 293.8 | 500 |
| SIG | ML-DSA-44 | keygen | native | 109.9 | 500 |
| SIG | ML-DSA-44 | sign | native | 603.4 | 500 |
| SIG | ML-DSA-44 | verify | native | 114.9 | 500 |
| SIG | ML-DSA-65 | keygen | native | 191.3 | 500 |
| SIG | ML-DSA-65 | sign | native | 900.9 | 500 |
| SIG | ML-DSA-65 | verify | native | 174.0 | 500 |
| SIG | ML-DSA-87 | keygen | native | 265.9 | 500 |
| SIG | ML-DSA-87 | sign | native | 1,118.0 | 500 |
| SIG | ML-DSA-87 | verify | native | 299.6 | 500 |
| KEM | X25519 | keygen | classical | 50.2 | 500 |
| KEM | X25519 | exchange | classical | 44.9 | 500 |
| KEM | ECDH P-256 | keygen | classical | 30.0 | 500 |
| KEM | ECDH P-256 | exchange | classical | 70.7 | 500 |
| KEM | RSA-2048 OAEP | keygen | classical | 52,193.1 | 25 |
| KEM | RSA-2048 OAEP | encrypt | classical | 42.7 | 500 |
| KEM | RSA-2048 OAEP | decrypt | classical | 746.1 | 500 |
| SIG | Ed25519 | keygen | classical | 34.7 | 500 |
| SIG | Ed25519 | sign | classical | 34.8 | 500 |
| SIG | Ed25519 | verify | classical | 100.4 | 500 |
| SIG | ECDSA P-256 | sign | classical | 27.3 | 500 |
| SIG | ECDSA P-256 | verify | classical | 80.7 | 500 |
| SIG | RSA-2048 PSS | sign | classical | 750.3 | 500 |
| SIG | RSA-2048 PSS | verify | classical | 42.8 | 500 |

## Native against pure Python

| Algorithm | Operation | Pure (us) | Native (us) | Faster by |
| --- | --- | ---: | ---: | ---: |
| ML-KEM-768 | keygen | 3,270.1 | 186.5 | 17.5x |
| ML-KEM-768 | encapsulate | 4,093.2 | 60.5 | 67.7x |
| ML-KEM-768 | decapsulate | 6,896.0 | 220.1 | 31.3x |
| ML-KEM-1024 | keygen | 4,759.3 | 261.9 | 18.2x |
| ML-KEM-1024 | encapsulate | 5,781.7 | 83.6 | 69.2x |
| ML-KEM-1024 | decapsulate | 8,234.8 | 293.8 | 28.0x |
| ML-DSA-44 | keygen | 6,324.7 | 109.9 | 57.5x |
| ML-DSA-44 | sign | 27,700.7 | 603.4 | 45.9x |
| ML-DSA-44 | verify | 7,087.4 | 114.9 | 61.7x |
| ML-DSA-65 | keygen | 9,622.6 | 191.3 | 50.3x |
| ML-DSA-65 | sign | 44,079.7 | 900.9 | 48.9x |
| ML-DSA-65 | verify | 13,299.6 | 174.0 | 76.4x |
| ML-DSA-87 | keygen | 14,894.3 | 265.9 | 56.0x |
| ML-DSA-87 | sign | 69,478.8 | 1,118.0 | 62.1x |
| ML-DSA-87 | verify | 16,679.0 | 299.6 | 55.7x |
