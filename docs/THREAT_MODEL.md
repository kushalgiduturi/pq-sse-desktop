# Threat model

PQ-SSE Desktop and the PQ-SSE server, as built on branch `reallife` (milestone 7 of `REALLIFE_PLAN.md`).
This describes what the system tries to protect, from whom, and what it does not try to do. It is the
author's own analysis, written with the code and the tests at hand. It is **not** an audit, and it has not
been reviewed by anyone else.

## 1. The system in one paragraph

A **data owner** encrypts documents and a keyword index on their own computer and stores them on a
**cloud server** they do not have to trust. **Receivers** approved by the owner search the index with
tokens and decrypt the results. The server answers searches without learning the keywords or the text, and
every answer is checked against the owner's signed state. The cryptographic scheme is the MU-PQ-SSE v3 paper
(`docs/PAPER_CONFORMANCE.md`): ML-KEM and ML-DSA for keys and signatures, HMAC-SHA3-256 as the PRF,
AES-256-GCM for data, HKDF-SHA3-256. In the networked mode the parties talk over TLS with a pinned
certificate (`docs/SERVER.md`). In the local demo everything runs on one PC.

## 2. Assets

| Asset | Where it lives | Why it matters |
| --- | --- | --- |
| Document text and titles | the owner's vault (plain, encrypted at rest); the server (AES-GCM ciphertext) | the main secret |
| Keywords and the search history | the owner's vault; receivers' tokens (derived, not plain) | reveals what a document is about and what people look for |
| Group keys per epoch | the owner's vault; each receiver's capability; escrow boxes at the server (under the owner's recovery key) | decrypt documents and the index |
| Owner signing key (ML-DSA) | the owner's vault | whoever holds it can change the collection undetected |
| Receiver keys (ML-KEM, ML-DSA), credential `a_u`, `m_u` | the receiver's vault; `a_u` also at the server (sealed in its store) | access to the groups granted |
| Server keys (ML-KEM, ML-DSA), TLS key, admin token | the server's data folder | open control messages, sign search responses, run the operator interface |
| Passphrases and the owner recovery key | people's heads; the vaults (recovery key) | unlock all of the above |
| Integrity of results | the owner's signatures and the hash chains | a wrong or incomplete answer must be detected |

## 3. Who might attack, and what they can do

| Actor | Capability assumed | Goal |
| --- | --- | --- |
| **A1 Honest-but-curious server** | runs the server code faithfully, reads everything it stores and sees | learn keywords, text, who searches what |
| **A2 Malicious server** | changes, drops, replays or reorders anything it stores or sends | make receivers accept wrong, stale or incomplete results; impersonate the owner |
| **A3 Network attacker** | reads and changes traffic between the parties | read data, impersonate the server, replay requests |
| **A4 Revoked receiver** | keeps every key and ciphertext it ever had; may watch the network; may collude with A1 | read data added after revocation (R) or any data (RE) |
| **A5 Other receivers** | approved for some groups | reach groups outside their scope |
| **A6 Stranger on the internet** | can reach the server's port | flood it, crash it, join without an invite, read others' mail |
| **A7 Other user on the same PC** | an ordinary account, no administrator rights | read another user's vaults or the server's keys |
| **A8 Thief of a powered-off laptop or a backup file** | has the files, not the passphrase | open the vault or backup offline |
| **A9 Future quantum computer** | records traffic and ciphertexts now, breaks classical public-key cryptography later | read today's data later ("harvest now, decrypt later") |
| **A10 Supply chain** | a changed dependency, installer or update | run code on users' computers |

## 4. Trust boundaries

1. **Owner's computer ↔ server.** Everything crossing it is encrypted or a pseudorandom token, and every
   owner message is signed. TLS 1.2+ with a pinned certificate wraps it in the networked mode.
2. **Receiver's computer ↔ server.** Requests are encrypted under the receiver's credential; replies are
   signed by the server and checked against the owner's signed state.
3. **Owner ↔ receiver.** There is no direct channel: invites, the one-time code and the six fingerprint words
   travel by channels the people choose (a file, a call). The keys travel through the server, sealed with
   ML-KEM and signed.
4. **Operator ↔ server.** The admin port listens on 127.0.0.1 only and needs a token. Its replies hold counts
   and sizes, never content.
5. **Process ↔ files on disk.** The vaults are encrypted under passphrase-derived keys. The key files are
   readable by their account only.

## 5. Threats, defences and what is left

`T` = tested (the test file is named), `D` = documented limit.

| # | Threat | Defence | Evidence | Left over |
| --- | --- | --- | --- | --- |
| 1 | A1 reads documents or keywords | AES-256-GCM per document under per-epoch keys; index entries are PRF outputs; states encrypted and padded to `N_max` | T `test_m3_http.py` (no plaintext or key bytes in the store files), `test_m15_paper.py` (leakage profile) | D: the leakage the paper allows (Section 8 below) |
| 2 | A2 returns wrong, stale or incomplete results | owner-signed states with expiry; hash chains; server-signed, encrypted responses; eight checks of Algorithm 8 | T `test_m2_tamper.py`, the Security Lab (11 scenarios, `test_m5_app.py`) | D: within the freshness window (24 h by default) a server can serve the previous state and hide newer documents |
| 3 | A2 forges owner actions (updates, grants, rekeys, invites) | ML-DSA signatures on every owner message; sequence numbers; `duplicate` and `bad_sequence` | T `test_m2_protocol.py`, `test_m17_client.py`, `test_m25_access_change.py` | none known |
| 4 | A2 forges the owner's invite proof | two keys from the one-time code; the server holds only `k_server` | T `test_m18_invites.py::test_the_server_cannot_forge_the_owners_invite_proof` | D: someone who has the invite file **and** the code can join once; the owner still approves after the fingerprint words |
| 5 | A3 impersonates the server | certificate pinning before any request byte; the server's PQ key fingerprint checked against the invite | T `test_m16_server.py::test_wrong_pin_is_refused_before_any_request` | D: TLS key exchange is classical (ECDHE); see 13 |
| 6 | A3 replays requests | timestamps (300 s window) and nonces on joins, mail and listing; sequence numbers on owner messages | T `test_m19_network_faults.py` (replayed join, clock skew) | D: a search request replayed inside its window gets the same encrypted answer, which reveals nothing new |
| 7 | A4 reads data after revocation | policy R (new epoch, rekey boxes only to the rest), RE (everything re-encrypted, old segments dropped); the server refuses the credential at once | T `test_m2_revocation.py`, collusion scenario in the Security Lab | D: under R a revoked receiver keeps what it could read before |
| 8 | A4 after a partial removal of one group | the scope check at once, then a rotation of that group | T `test_m25_access_change.py` | as 7, per group |
| 9 | A5 reaches other groups | the server's scope check before any lookup; capabilities hold only granted groups' keys | T `test_m2_protocol.py::test_scope_confinement` | none known |
| 10 | A6 joins without an invite, lists joins, reads mail | invites required on the networked server; signed `join_list` and `mail_get` | T `test_m18_invites.py` | none known |
| 11 | A6 floods or crashes the server | body limits, rate limits per address and per credential, connection cap, per-connection deadline, rollback on any failure; random and malformed bodies | T `test_m16_server.py`, `test_m19_network_faults.py`, fuzzing `test_m28_fuzz.py` | D: the standard-library HTTP server is meant for a small group. Facing the internet, put a reverse proxy with its own limits in front |
| 12 | A6 reaches the operator interface | admin port on 127.0.0.1, token, refuses non-local clients | T `test_m16_server.py::test_admin_interface_refuses_a_public_address` | D: anyone with a shell on the server as that account can read the token |
| 13 | A9 harvests traffic now | the data inside TLS is protected by ML-KEM and ML-DSA, not by TLS. A recorded TLS session, once its classical exchange is broken, shows only what A1 sees | design (`docs/SERVER.md`) | D: metadata inside TLS (sizes, timing, which endpoint) becomes visible to A9. Post-quantum TLS is not used |
| 14 | A7 reads another account's key files | vaults, server store, TLS key, admin token and backups restricted to their account (icacls or 0600) | T `test_m21_keys.py` | D: administrators and the operating system can read everything |
| 15 | A8 opens a stolen vault or backup | scrypt (N = 2^15 for vaults, 2^17 for backups and exports), AES-256-GCM; minimum passphrase lengths (8, 12) | T `test_m21_keys.py`, `test_m24_export_and_log.py` | D: a weak passphrase can be guessed offline; there is no rate limit on a copied file |
| 16 | Malware on the owner's or a receiver's computer | none beyond auto-lock (15 min) and overwriting the vault key on lock (best effort) | T `test_m21_keys.py::test_bridge_auto_lock` | D: out of scope; keys in use are in memory |
| 17 | The owner crashes or restores an old backup | write-ahead journal; recovery from escrow with policy RE rebuild | T `test_m22_journal.py`, `test_m26_recovery.py` | D: invites made after the backup are lost |
| 18 | One owner interferes with another on a shared server | separate store per owner; signatures checked against that owner's key | T `test_m27_owners.py` | D: the operator sees every owner's sizes and timing |
| 19 | Malicious document or PDF on import | size limits before parsing; text length cap; parsing errors become a refusal | T `test_m28_fuzz.py` | D: pypdf runs in the app's process; a PDF that triggers a parser bug could still crash the app |
| 20 | A10 a changed dependency or installer | pinned versions (`requirements-lock*.txt`), the update check and the web installer accept only files whose SHA-256 and Inno Setup signature (ECDSA P-256, `app/issig.py`) match the key built into the app, `pip-audit`, an SBOM | `docs/SBOM.cdx.json`, `docs/SECURITY_REVIEW.md` | D: the program files are not code signed (`docs/DISTRIBUTION.md`); builds are not bit-for-bit reproducible (Section 9 of the review) |
| 21 | Logs leak secrets | no keys, passphrases, codes or document text in logs or admin replies | T `test_m16_server.py::test_admin_needs_the_token_and_shows_no_secrets`, `docker_e2e.py` (operator view has no document words) | none known |

## 6. Assumptions

- The owner's and receivers' computers are not compromised while keys are unlocked.
- People compare the six fingerprint words, and send the one-time code by a second channel.
- Clocks agree within about two minutes; the app warns above that and refuses above five.
- ML-KEM, ML-DSA, SHA3, HMAC, HKDF and AES-GCM are secure, and OpenSSL implements them correctly. The
  pure-Python fallback is **not constant time** and is for teaching only. Constant-time behaviour of the
  native code is not claimed beyond what the OpenSSL project documents for its build.

## 7. Out of scope

Traffic analysis beyond the paper's leakage functions; denial of service by an attacker with more bandwidth
than the server; physical attacks; a malicious data owner (the owner controls its own collection);
backdoored hardware; side channels in the pure-Python code.

## 8. What the server learns by design

As in the paper's leakage functions: the number of entries per update batch, the access pattern (which
stored entries a search touches) and the search pattern (repeated tokens within an epoch), document
ciphertext sizes, the power-of-two range of each group's keyword count (`N_max`), the time of each request,
which receiver sends it, and which state versions a receiver already holds (design note 005 B). Document
identifiers are hidden behind handles. Since design note 006 C it also stores escrow boxes it cannot open.
