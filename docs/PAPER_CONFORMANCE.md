# Conformance of the code to the paper

Paper: "PQ-SSE: Integrating ML-KEM into Searchable Symmetric Encryption. A Three-Party, Multi-User,
Dynamic and Verifiable Construction" (13 pages, read in full on 2026-11-18 from
`docs/paper/MU-PQ-SSE_v3_Journal_Paper.pdf`, which is kept out of git). Code: branch `reallife`,
`pqsse/` (owner, receiver, cloud, core). The README said the code was built from a specification, not
from the paper; this is the first item-by-item comparison.

How it was checked: every definition, algorithm, theorem, leakage statement and evaluation claim was
read in the paper and looked up in the code (file and function), then matched to the tests that
exercise it. Proofs are not re-proved here: for a theorem, "matches" means the code meets the
theorem's assumptions and its checkable consequences are tested. New tests for this report:
`tests/test_m15_paper.py` (4 property tests, and 3 strict expected-failure tests that confirm
deviations P-01 to P-03 in running code).

Verdicts: **matches**, **deviates** (differs in a way that matters or may matter), **extends** (does
more than the paper, or the same thing in a different form, without weakening it), **missing**,
**cannot tell**.

## Decisions needed (summary)

Rule 2 of the brief: nothing below was changed. Each item waits for your decision.

| # | What differs | Security relevant | My recommendation |
| --- | --- | --- | --- |
| P-01 | The server's search response is signed but **not encrypted** under the receiver's credential (paper Algorithm 7 step 5: `rho = AE.Enc(a_u, R; res||u)`). A network observer sees the returned addresses and masked values. A revoked receiver who still holds old-epoch keys and can watch the network could unmask other receivers' results in old segments without any help from the server. The paper's Section II-G and IV-A claims ("network observers, including revoked receivers, do not see which addresses are searched") do not hold for this code | **Yes** | Change the code to the paper: encrypt the response body under the token key and sign `H(token) || H(ciphertext)`. Small protocol change, needs the design note and your approval. TLS in the networked mode hides it from outsiders too, but TLS uses classical key exchange today, so it does not give the paper's post-quantum guarantee |
| P-02 | Control messages (group setup, credential, deauth, epoch) are signed and sequence-numbered but **not sealed** to the server (paper Section II-A: `Ctl(m) = (Seal_pkCS(DO-CS, n||m), Sign(...))`). Credentials and rekey keys inside them are sealed, so no key leaks; group names, user ids, epochs and the reset flag are visible to a network observer | Yes, metadata only | Change the code to the paper (seal the control payload to the server's ML-KEM key). Small protocol change |
| P-03 | The state capacity `N_max` **doubles** when a group outgrows it (`fit_nmax`), so the state size tells the server the power-of-two range of the keyword count. The paper fixes `N_max` at Setup and design goal G7 says the server "does not learn the number of keywords" | Yes, small leak | Either (a) fix the capacity per group and refuse to publish past it, or (b) keep doubling and change the paper's G7 and Section II-G text to say the range leaks. I lean to (b) with a large default, and saying so plainly |
| P-04 | Join proof: the paper has the owner send a fresh nonce (challenge). The code lets the receiver choose the nonce and adds a timestamp; the owner rejects a stale timestamp (600 s window) or a nonce it has seen (last 500 kept) | Low | Change the paper to describe the non-interactive variant (the mailbox has no owner-to-receiver path before approval), with its replay window stated |
| P-05 | Rekey boxes are bound to `m_v` as in the paper **and also signed** by the owner. The paper says rekey messages need no signature and its revocation timings (Fig. 8, Table IV) assume that | No (adds protection) | Keep the signature and change the paper's cost formula, or drop it to match the paper's cost. I lean to keeping it and updating the text |
| P-06 | On revocation the server marks the credential revoked but keeps the wrapped `a_u`. The paper deletes `a_u*` and `S_u*` | Low | Change the code: delete the wrapped key, keep only a revoked marker so the error stays clear. Storage only, no message change |
| P-07 | The paper's evaluation (Section III, Tables I to IV, Figs. 5 to 9) used liboqs 0.16.0, classical baselines (X25519/Ed25519, ECDH/ECDSA P-256, RSA-2048) and a Linux VM. This repository has no liboqs, no classical baselines and no experiment scripts for those figures, so **none of the paper's numbers can be reproduced from this code** | Not security, but scientific | Decide which artifact backs the paper's numbers. Part C (liboqs default) gets the PQ numbers closer; the classical baselines would need a separate benchmark harness |
| P-08 | Test counts differ from Table I (for example 375 queries in the paper, at least 300 here; 150 trials per tamper type in the paper, 100 here) | No | Align the test counts with Table I, or the table with the tests, once P-07 is decided |

Everything else is a match or an extension listed below; none of those needs a decision.

### Decisions (2026-11-18: all recommendations accepted)

| # | Decision | Done |
| --- | --- | --- |
| P-01 | Code changed to the paper: the search response is encrypted under the receiver's token key | design note 001; `test_m15_paper.py::test_search_response_hides_the_searched_addresses_from_the_network` passes |
| P-02 | Code changed to the paper: control messages are sealed to the cloud's ML-KEM key | design note 001; `test_control_messages_are_confidential_on_the_network` passes |
| P-03 | Doubling kept; default capacity raised to 4,096 records; the paper text changes | `docs/PAPER_CHANGES.md`; `test_state_size_is_fixed_up_to_the_capacity_and_doubles_beyond_it` |
| P-04 | Paper text changes to the receiver-nonce variant | `docs/PAPER_CHANGES.md` |
| P-05 | Rekey signature kept; paper cost formula changes | `docs/PAPER_CHANGES.md` |
| P-06 | Code changed: the server erases a revoked receiver's wrapped `a_u` | design note 001; `test_revoked_credential_is_erased_at_the_server` |
| P-07 | Milestone 5 adds liboqs and a classical-baseline benchmark harness; the paper names its artifact | `docs/PAPER_CHANGES.md`, `REALLIFE_PLAN.md` |
| P-08 | Test counts aligned with Table I after P-07 | milestone 5 |

The verdict tables below show the state at the time of the review (before these changes).

## Primitives and building blocks (Section II-A)

| Paper item | Requires | Code | Tests | Verdict |
| --- | --- | --- | --- | --- |
| KEM | ML-KEM-768, IND-CCA | `pqsse/pqbackend.py` (kyber-py; liboqs path untested); default `Params()` = ML-KEM-768 | `test_m1_core.py::test_kem_round_trip`, `test_m2_correctness.py::test_every_parameter_set_end_to_end` | matches (512 and 1024 also offered) |
| SIG | ML-DSA-65, EUF-CMA | `pqbackend.py` (dilithium-py); default ML-DSA-65 | `test_m1_core.py::test_signature_round_trip` | matches |
| F | HMAC-SHA3-256 | `core/prims.py::F`, batch `gpu/batchprf.py` | `test_m1_core.py::test_primitives_match_standard_library`, `test_m4_gpu.py` | matches |
| H | SHA3-256 | `prims.py::H` | same | matches |
| AE | AES-256-GCM, random 96-bit nonce | `prims.py::aead_encrypt` | `test_m1_core.py::test_aead_detects_tampering` | matches |
| KDF | HKDF-Expand, SHA3-256 | `prims.py::hkdf` (full HKDF with salt); subkeys add `sstr(g) || u32(e)` to the label | `test_m1_core.py::test_index_derive_matches_definition` | extends (more context bound) |
| Definitions 1 to 3 | security notions of KEM, SIG, PRF, AE, H | assumptions, not code | none possible | cannot tell (assumptions) |
| Sealed delivery | `KDF(ss||psk, label)`, `AE.Enc(key, m; ad)` | `core/seal.py`: `HKDF(ikm=ss, salt=psk, info="pqsse/v3/seal"||H(kem_ct))` | `test_m1_core.py::test_seal_unseal`, `test_seal_with_pre_shared_key` | extends (binds the KEM ciphertext; psk as salt) |
| Control channel | sealed to the CS, signed, counter `n` | `owner.py::_ctl`, `cloud/core.py::_h_ctl`: signed, counter checked, payload **not sealed** | `test_m15_paper.py::test_control_messages_are_confidential_on_the_network` (xfail) | **deviates: P-02** |
| Signatures | `Sign(sk, label || m)` | `core/signing.py`: `label || 0x00 || SHA3-256(payload)` | `test_m1_core.py::test_signing_is_domain_separated` | extends (hash then sign, domain separated) |

## Model and definitions (Sections II-B, II-C)

| Paper item | Requires | Code | Tests | Verdict |
| --- | --- | --- | --- | --- |
| Three parties, threat model | DO honest; CS honest-but-curious for privacy, malicious for integrity; malicious receivers; quantum network adversary; authentic public keys; loose clocks | roles in `pqsse/owner`, `pqsse/receiver`, `pqsse/cloud`; public keys through `.pqpub` files and fingerprints (`core/pairing.py`) | `test_m2_*`, `test_m3_http.py` | matches for the CS and receivers; the network adversary is affected by P-01 and P-02 |
| G1 owner authenticity | CS accepts only DO-signed batches in sequence | `cloud/core.py::_h_update` | `test_m2_protocol.py::test_forged_modified_replayed_and_out_of_order_updates_are_rejected` | matches |
| G2 scoped delegation | authenticated Join, keys only for the scope, PQ-confidential | `owner.py::check_join`, `approve_join` | `test_m2_protocol.py::test_join_with_wrong_proof_of_ownership_is_rejected`, `test_a_capability_only_opens_for_its_receiver` | matches (Join nonce: P-04) |
| G3 authorization | valid tokens of current receivers, in scope, current epoch | `cloud/core.py::_open_request`, `_scoped_group`, `_h_search` | `test_m2_protocol.py::test_scope_confinement`, `test_stale_token_timestamp_is_rejected`, `test_m2_revocation.py` | matches |
| G4 verifiability | provenance, integrity, completeness, freshness | `receiver.py::_verified_states`, `_search` (eight checks) | `test_m2_tamper.py`, `test_m2_protocol.py` | matches |
| G5 revocation | revoked receiver loses access; old keys open nothing new (R) or nothing stored (RE) | `owner.py::revoke`, `_rotate` | `test_m2_revocation.py`, Security Lab collusion scenario | matches |
| G6 forward and backward privacy | see Definitions 6, 7 | see below | see below | matches |
| G7 leakage reduction | CS does not learn the number of keywords | padded state, but capacity doubles | `test_m15_paper.py::test_state_size_does_not_depend_on_the_number_of_keywords` (xfail) | **deviates: P-03** |
| Definition 4 syntax | ten algorithms | all ten present (table below) | `test_m8_learn_core.py::test_each_of_the_ten_algorithms_emits_its_event` | matches |
| Definition 5 adaptive L-security | simulation-based | proof property | none possible | cannot tell (proof); the leakage it is stated for is tested below |
| Definition 6 forward privacy | update leakage independent of `w` | fresh counter addresses per keyword | `test_m2_protocol.py::test_forward_privacy_new_updates_share_no_address_with_old_tokens`, `test_m15_paper.py::test_update_leakage_is_group_entry_count_and_document_handles_only` | matches |
| Definition 7 Type-II backward privacy | search leakage `(g, sp, TimeDB, Updates)` | masked `(op || id)`; tokens cover all entries of `w` | `test_m15_paper.py::test_type_ii_backward_privacy_add_and_delete_entries_look_alike`, `test_search_leakage_is_search_pattern_and_update_history_of_the_keyword` | matches |
| Definition 8 verifiability with freshness | reject results differing from `DB_g(w)` at any acceptable version | `_verified_states` + `_search` | `test_m2_tamper.py` (5 tamper types x 100 trials, unsigned and wrongly signed responses, modified and swapped documents) | matches |
| Definition 9 update authenticity | reject forged, reordered, repeated batches | `_h_update` | as G1 | matches |
| Definition 10 scope confinement | no answer outside the scope; documents and states of other groups stay hidden | `_scoped_group`; group keys only in capabilities of the scope | `test_m2_protocol.py::test_scope_confinement`, `test_receiver_without_capability_cannot_search` | matches |
| Definition 11 revocation security | (i) no answer after revocation; (ii) R: new data hidden; RE: all stored data hidden | `revoke`, `_ctl_deauth`, `_rotate` | `test_m2_revocation.py::test_revoke_policy_r`, `test_revoke_policy_re`, `test_r_then_re_then_new_member` | matches; P-01 weakens the network part for policy R |
| Definition 12 correctness | honest runs return `DB_g(w)` and documents | whole flow | `test_m2_correctness.py::test_random_workload_matches_plaintext_reference`, `test_m15_paper.py::test_receivers_search_results_survive_add_delete_add_across_epochs` | matches |

## Key hierarchy and data structures (Section II-D, Figs. 2 and 4)

| Paper item | Requires | Code | Tests | Verdict |
| --- | --- | --- | --- | --- |
| Long-term keys | DO SIG; CS KEM + SIG; receiver KEM + SIG | `Owner.create`, `CloudCore._setup`, `Receiver.create` | `test_m1_core.py`, `test_m2_protocol.py` | matches |
| Group and epoch keys | independent 256-bit `K_g^e`, new key per revocation | `owner.py::create_group`, `_rotate` (`random_key()`) | `test_m2_revocation.py` | matches; epochs start at **1**, the paper at 0 (not security relevant, no change proposed) |
| Derived keys | `K_idx, K_doc, K_st = KDF(K_g^e, label)` | `prims.py::group_subkeys` | `test_m1_core.py::test_index_derive_matches_definition` | extends (adds `g`, `e`) |
| Capability | `cap_u = (a_u, m_u, {K_g^e : g in S_u, b_g <= e <= e_g})` | `approve_join`: `{uid, a, m, groups: {g: {base, keys base..epoch}}}` | `test_m2_protocol.py::test_a_capability_only_opens_for_its_receiver` | matches (PLAN.md D6 is the paper's definition, not a deviation) |
| Index entry | `a_i = F(K_idx, w||i||0)`, `v_i = (op||id) XOR F(K_idx, w||i||1)[0:5]`, i from 1 | `core/index.py`: same, with `sstr(w)` length prefix, i from **0** | `test_m1_core.py::test_index_derive_matches_definition` | matches (index base differs, not security relevant) |
| Hash chain | `d_0 = 0^256`, `d_i = H(d_{i-1}||a_i||v_i)` | `core/chain.py` | `test_m1_core.py::test_hash_chain` | matches |
| State record | 44 bytes `H(w)[0:8]||c_w||d_w`, padded to `N_max`, encrypted as a whole | `core/state.py` (`RECORD_LEN = 44`) | `test_m2_protocol.py::test_receiver_forged_state_is_rejected` | matches; padding capacity P-03 |
| State header | `(g, e, ver, t_exp, final)`, signed with `H(ct)` | adds `base` (PLAN.md D7); `t_exp` in ms; version only in the header | `test_m2_protocol.py::test_state_rollback_is_rejected`, `test_hiding_a_new_epoch_is_detected` | extends: the receiver reads `b_g` from the DO-signed header instead of its own key list; a forged base would need a DO signature, so I see no weakness |

## The ten algorithms

| Algorithm | Requires (paper) | Code | Tests | Verdict |
| --- | --- | --- | --- | --- |
| 1 Setup | keys; `K_g^0`; `Ctl(group, g)` | `Owner.create`, `create_group` (+ empty state publish), `CloudCore._setup`, `_ctl_group` | `test_m1_core.py`, `test_m2_correctness.py` | matches (Ctl unsealed: P-02) |
| 2 Join | DO nonce; receiver proof `Sign(join||u||pk||n)`; `Ctl(auth, u, a_u, S_u)`; capability sealed to `pk_u` and DO-signed | `Receiver.join_request` (own nonce + timestamp), `Owner.check_join`, `approve_join`, `CloudCore._ctl_cred`, `Receiver.accept_capability` | `test_m2_protocol.py` join tests | **deviates: P-04** (nonce source); rest matches |
| 3 BuildIndex | entries, documents `AE.Enc(K_doc, D; g||e||id)`, `sigma_id = Sign(doc||g||e||id||H(C))`, one batch | `Owner.build_index` -> `_apply`; document signed over `[g, e, handle, H(blob)]` with `handle = F(K_doc, "handle"||id)[0:16]` (PLAN.md D9) | `test_m2_correctness.py`, `test_m2_tamper.py::test_swapped_documents_are_rejected` | extends: the server never sees document ids (the paper's L_Upd reveals them); the receiver recomputes the handle from the id, so the binding holds |
| 4 Update | batch `g||e||seq||E||C||Del` signed; CS checks signature, epoch, `seq+1`; delete removes ciphertexts | `_apply` (adds `reset` for RE), `CloudCore._h_update` (also refuses a reset flag that does not match a pending RE, and duplicate addresses) | `test_m2_protocol.py` update tests | matches, with extra server checks |
| 5 Publish | `ver+1`, padded records, `t_exp = now + Delta` or infinity if final, signed header | `Owner.publish`, `make_state`; server keeps only newer versions and refuses changes to a final segment | `test_m2_protocol.py` state tests | matches (capacity: P-03; final states carry a finite `exp` that the receiver ignores for final segments) |
| 6 TokenGen | addresses for every segment `b_g..e_g` with `c > 0`, `T = AE.Enc(a_u, g||e_g||ctr||A; tok||u)` | `Receiver._search` (first half): token key `HKDF(a_u, "pqsse/v3/token")`, includes all segments, a timestamp and a nonce instead of `ctr` (PLAN.md D8) | `test_m2_protocol.py::test_stale_token_timestamp_is_rejected` | extends (replay window instead of counter; segments with `c = 0` are sent as empty lists, which the paper's size formula `8s` also implies) |
| 7 Search | refuse revoked; open `T`; check scope and epoch; `rho = AE.Enc(a_u, R; res||u)`; `sigma_R = Sign(resp||H(T)||H(rho))` | `CloudCore._h_search`, `sign_response`: everything except the response encryption | `test_m15_paper.py::test_search_response_hides_the_searched_addresses_from_the_network` (xfail) | **deviates: P-01** |
| 8 Verify | CHECKSTATE (signature, all segments, older final, fresh, no rollback); CHECKRESULT (CS signature, length, chain, unmask in epoch order) | `Receiver._verified_states`, `_search` (second half): the same checks as eight named checks, plus "the cloud presented an older epoch than a key I hold" and an exact address comparison | `test_m2_tamper.py`, `test_m2_protocol.py`, `test_m5_app.py::test_every_attack_lab_scenario_behaves_as_claimed` | matches (and extends) |
| 9 Decrypt | request `AE.Enc(a_u, X; doc||u)`; check `sigma_id`; key for `(g, e)`; `AE.Dec` | `Receiver.open_document`, `decrypt_document`, `CloudCore._h_doc_get` (one document per request) | `test_m2_tamper.py::test_modified_documents_are_rejected`, `test_swapped_documents_are_rejected` | matches (handles: see Algorithm 3) |
| 10 Revoke | `Ctl(deauth)` and CS deletes `a_u*`; final publish; new epoch key; `Ctl(epoch)`; rekey `Seal(..., psk = m_v)`; RE: `b_g <- e_g` and reset rebuild; publish | `Owner.revoke`, `_rotate`, `CloudCore._ctl_deauth` (marks revoked, keeps wrapped `a_u`), `_ctl_epoch` (refuses an epoch change without a final state), `Receiver._accept_rekey` (rekey also owner-signed) | `test_m2_revocation.py` (4 tests), `test_m2_protocol.py::test_rekey_box_is_bound_to_the_pre_shared_key` | **deviates: P-05, P-06**; rest matches |

## Theorems and leakage (Sections II-E to II-G)

| Paper item | Statement | What the code provides | Tests | Verdict |
| --- | --- | --- | --- | --- |
| Theorem 1 correctness | honest runs correct except `q_k delta + q_K Adv_prf + q_u^2/2^257` | distinct inputs `sstr(w)||u32(i)||b`, epoch order in decoding | `test_m2_correctness.py` (at least 300 queries against a plaintext reference, every parameter set end to end), `test_m15_paper.py::test_receivers_search_results_survive_add_delete_add_across_epochs` | matches (proof not re-checked) |
| Theorem 2 adaptive security, FP, Type-II BP | game sequence G0 to G5 | the simulated quantities are what the code leaks, except P-01 and P-02 for the network part of A's view (Definition 5 gives A "all network traffic") | `test_m15_paper.py` leakage tests, `test_m2_protocol.py` forward privacy | **deviates** for the network view until P-01 and P-02 are decided; matches for the server view |
| Theorem 3 verifiability | reduction to EUF-CMA, CR of H, PRF | all checks of Algorithm 8 present | `test_m2_tamper.py` | matches |
| Theorem 4 update authenticity | reduction to EUF-CMA | signature, epoch, sequence checks | `test_m2_protocol.py` | matches |
| Theorem 5 scope confinement | no answer outside the scope; impersonation bounded by KEM, KDF, AE | scope check before any lookup; capability sealed to `pk_u` | `test_m2_protocol.py::test_scope_confinement` | matches |
| Theorem 6 revocation security | (i) no answer after revocation; (ii) R hides new data; (iii) RE hides all stored data | as Algorithm 10 | `test_m2_revocation.py`, Security Lab collusion scenario (R: old documents readable, RE: none) | matches for (i) to (iii); P-01 lets a revoked receiver who watches the network learn other receivers' old-segment results under R |
| Corollary 1 post-quantum | Theorems 2 to 6 against quantum adversaries | ML-KEM and ML-DSA through pure-Python libraries (not constant time); TLS in the planned network mode is classical | none possible | cannot tell (proof); note that a classical TLS layer does not change the paper's argument because the protocol does not rely on it |
| L_Stp | groups and `N_max` | groups in control messages; `N_max` grows (P-03) | `test_m15_paper.py` | deviates (P-03) |
| L_Upd | group, number of entries, identifiers and sizes of added or deleted documents | group, number of entries, document handles (not ids), sizes | `test_m15_paper.py::test_update_leakage_is_group_entry_count_and_document_handles_only` | extends (less: handles, not ids) |
| L_Srch | `(g, sp_g(w), Updates_g(w))`, plus `DB_g(w)` on fetch | the same; fetch reveals handles | `test_m15_paper.py::test_search_leakage_is_search_pattern_and_update_history_of_the_keyword` | matches |
| L_Usr | identity and scope of joiner or revoked receiver, number of remaining receivers per group, RE size | credential box gives scope; one rekey box per remaining receiver; RE batch size | `test_m2_revocation.py` | matches |
| Section II-G leakage reduction | fresh addresses; masked op and id; padded state hides keyword count; tokens and responses encrypted under the credential | first two match; padding P-03; responses P-01 | `test_m15_paper.py` | deviates (P-01, P-03) |

## Evaluation claims (Section III)

| Paper item | Claim | In this repository | Verdict |
| --- | --- | --- | --- |
| III-A setup | Python 3.11, liboqs 0.16.0, `cryptography` 46.0.7, classical baselines, 2-vCPU Xeon VM | Python 3.11.9, pure-Python ML-KEM and ML-DSA, `cryptography` from `requirements.txt`, no classical baselines | **missing: P-07** |
| Table I functional and security tests | 375/375 queries, 750/750 tampering, 50/50 unsigned responses, 0/200 links, R and RE collusion counts | the same kinds of tests exist with different counts (P-08); Security Lab shows R and RE collusion | extends in kind, counts differ (P-08) |
| Tables II to IV, Figs. 5 to 9 | timings and sizes | `pqsse/bench.py` measures the ten operations and BuildIndex on this machine with the pure-Python backend; no baselines, no Fig. 5 to 9 scripts | **missing: P-07** |
| Table V comparison | functionality of related schemes | literature claim | cannot tell (not code) |

## PLAN.md decisions reviewed

| Decision | Against the paper | Verdict |
| --- | --- | --- |
| D1 built from a specification | now compared item by item (this file) | closed |
| D4 one canonical wire encoding, signatures over `label || H(enc(m))` | form only | extends |
| D5 mailbox through the cloud | the paper does not fix the transport of join and rekey messages; the CS sees only sealed and signed blobs | matches |
| D6 capability carries all live segment keys | this is exactly the paper's `cap_u` | matches (not a deviation) |
| D7 `base` in the state header | extra field, DO-signed | extends |
| D8 token = explicit address list per segment | the paper's `A_e` | matches |
| D9 document handles | hides ids from the server | extends |
| D10 edit = delete + add, fresh id | allowed by Algorithm 4 | matches |
| D11 freshness `t_exp = publish + Delta`, final states do not expire | Algorithm 5 | matches |
| D12, D13 cloud passphrase and encrypted stores | implementation, outside the scheme | not in the paper |
| D14 to D20 | GPU, charts, tests, threads, logging, build | not in the paper |

The wire format (`docs/wire-format.md`) was checked against the code for every message in the table
above; it matches the code, and its differences from the paper are the ones listed here.
