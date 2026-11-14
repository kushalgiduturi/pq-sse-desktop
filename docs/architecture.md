# Architecture

Three parties with no shared in-memory state. Owner and receivers run inside the desktop
app; the cloud is its own process and is reached only through HTTP on 127.0.0.1.
Every message is a `pqsse.core.wire` encoded value.

```mermaid
flowchart LR
    subgraph APP["Desktop app process (PySide6)"]
        direction TB
        UI["Tabs: Owner, Receiver, Cloud, Attack Lab, Benchmarks, Settings"]
        OWN["owner/ : Setup, Join approval, BuildIndex, Update, Publish, Revoke"]
        REC["receiver/ : Join request, TokenGen, Verify, Decrypt"]
        PRF["gpu/ BatchPRF : CpuPRF (hashlib) or GpuPRF (CUDA Keccak kernel)"]
        OVAULT[("owner.sqlite\nAES-GCM under scrypt key")]
        RVAULT[("receiver_NAME.sqlite\nAES-GCM under scrypt key")]
        UI --> OWN
        UI --> REC
        OWN --> PRF
        REC --> PRF
        OWN --- OVAULT
        REC --- RVAULT
    end

    subgraph CLOUDP["Cloud process: python -m pqsse.cloud"]
        direction TB
        HTTP["cloud/server.py : HTTP on 127.0.0.1 only"]
        CORE["cloud/core.py : Update check, Publish store, Search, Revoke enforcement"]
        CDB[("cloud.sqlite\nindex entries, document ciphertexts,\nsigned states, credentials a_u, mailbox, log")]
        HTTP --> CORE
        CORE --- CDB
    end

    OWN -- "ctl, update, state_put (ML-DSA signed)" --> HTTP
    REC -- "states_get, search, doc_get (encrypted under a_u)" --> HTTP
    HTTP -- "entries + ML-DSA response signature" --> REC
    UI -. "admin_* with token: log, stats, what the server sees" .-> HTTP

    PUB["pubkeys/*.pqpub : pair devices (public keys only)"]
    OWN -. export / import .- PUB
    REC -. import .- PUB
    CORE -. export / import .- PUB
```

## Who holds what

| Secret | Owner | Receiver u | Cloud |
| --- | --- | --- | --- |
| Owner ML-DSA signing key | yes | no | no |
| Group keys `K_g^e` and derived `K_idx`, `K_doc`, `K_st` | yes | only groups in its capability | never |
| Receiver ML-KEM and ML-DSA secret keys | no | yes | no |
| Credential `a_u` | yes | yes | yes (wrapped under the cloud passphrase key) |
| Rekey key `m_u` | yes | yes | no |
| Cloud ML-KEM and ML-DSA secret keys | no | no | yes |
| Keywords, document text | yes | after Verify and Decrypt | never |

## Where the GPU is used

Only inside `BatchPRF`:

- `hmac_fixed` / `hmac_many`: the PRF `F = HMAC-SHA3-256` for addresses and masks
  (BuildIndex, Update, and TokenGen for long result lists).
- `sha3_fixed`: one hash chain "level" across many keywords at a time (BuildIndex, Update).

ML-KEM, ML-DSA, AES-GCM, HKDF, scrypt and everything in the cloud run on the CPU.
The GPU path is enabled only after its output matched `hashlib` and `hmac` byte for byte.

## Search, step by step

```mermaid
sequenceDiagram
    participant R as Receiver
    participant C as Cloud
    R->>C: states_get {uid, AES-GCM_a_u(g)}
    C-->>R: signed, encrypted states of segments base..current
    Note over R: check owner signatures, all segments present,<br/>older ones final, current one fresh, no rollback
    Note over R: TokenGen: c_w from the states,<br/>addresses a_0..a_{c_w-1} per segment
    R->>C: search {uid, AES-GCM_a_u(token)}
    Note over C: credential, not revoked, scope, epoch current
    C-->>R: entries + ML-DSA signature over (H(token), body)
    Note over R: response signature, completeness, hash chain,<br/>unmask, apply add / delete
    R->>C: doc_get {uid, AES-GCM_a_u(handle)}
    C-->>R: ciphertext + owner signature
    Note over R: Decrypt: verify owner signature, AES-GCM open
```
