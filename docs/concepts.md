# Concepts

Each idea three ways: the analogy used in the app, the real name, and where it lives in
the code. Where the analogy leaves something out, a **Simplification** line says what.

## The parties

| Analogy | Real name | Code |
| --- | --- | --- |
| Alice, the hospital records manager | Data owner | `pqsse/owner/owner.py` (`Owner`) |
| Bob and Carol, doctors | Receivers | `pqsse/receiver/receiver.py` (`Receiver`) |
| The rented storage company | Cloud server (untrusted) | `pqsse/cloud/core.py` (`CloudCore`), `pqsse/cloud/server.py` |

## Locking documents

**Analogy.** A document is a letter in a locked box. Everyone in a group shares the key
to that group's boxes.

**Real name.** Symmetric encryption with AES-256-GCM under a document key derived from
the group key.

**Code.** `Owner._apply` (encrypts), `Receiver.decrypt_document` (decrypts),
`pqsse/core/prims.py` (`aead_encrypt`, `group_subkeys`).

**Simplification.** There is one key per group and per key period, not one per box. Each
box also carries Alice's stamp, so a swapped box is noticed.

## Searching without unlocking

**Analogy.** Alice leaves the cloud a lookup table written in a secret code. Bob asks
the cloud "what is stored at these secret addresses?" The cloud fetches, without knowing
what the addresses stand for.

**Real name.** Searchable symmetric encryption (SSE). For word `w` and its `i`-th
occurrence, the address is `HMAC-SHA3-256(K_idx, w, i, 0)` and the stored value is the
document number masked with `HMAC-SHA3-256(K_idx, w, i, 1)`.

**Code.** `pqsse/core/index.py` (`derive`), `Owner._apply`, `Receiver._search`,
`CloudCore._h_search`.

**Simplification.** The cloud does learn how many entries matched and can notice when
the same addresses are requested again.

## The sealed search slip

**Analogy.** Bob writes the secret addresses on a slip and seals it so only the cloud
can read it.

**Real name.** Search token (TokenGen), encrypted with AES-256-GCM under a key derived
from Bob's credential `a_u`.

**Code.** `Receiver._seal_request`, `CloudCore._open_request`.

**Simplification.** Alice also knows Bob's credential, so she could read the slip too.
She already knows everything in it.

## Stamps

**Analogy.** Alice puts a tamper-proof stamp on everything she sends. The cloud stamps
its answers.

**Real name.** Digital signatures with ML-DSA (FIPS 204).

**Code.** `pqsse/core/signing.py`, `pqsse/pqbackend.py`.

## Sealed envelopes for keys

**Analogy.** Alice sends Bob his access pass in an envelope only Bob can open.

**Real name.** Key encapsulation with ML-KEM (FIPS 203), then AES-256-GCM. The package
is called the capability.

**Code.** `pqsse/core/seal.py` (`seal`, `unseal`), `Owner.approve_join`,
`Receiver.accept_capability`.

## The stamped summary and the running fingerprint

**Analogy.** Alice publishes a stamped note: "for each word there are this many entries,
and their running fingerprint is this". Bob compares the cloud's answer with the note.

**Real name.** The published state `ST_{g,e}` and a per-keyword hash chain
`d_i = SHA3-256(d_{i-1}, address_i, value_i)`.

**Code.** `pqsse/core/state.py`, `pqsse/core/chain.py`, `Owner.publish`,
`Receiver._verified_states`.

**Simplification.** The note is encrypted for group members and padded, so the cloud
does not learn the exact number of different words.

## Checking the cloud's answer

**Analogy.** Bob trusts Alice's stamp, not the cloud. Eight checks must pass before
anything is shown.

**Real name.** Verify (Algorithm 8).

**Code.** `Receiver._verified_states` and `Receiver._search`. The check names are in
`pqsse/receiver/receiver.py` (`CHECKS`).

## Freshness

**Analogy.** Every stamped note has a "use by" time, and Bob remembers the newest note
he has seen.

**Real name.** Freshness window (delta) and version monotonicity.

**Code.** `StateHeader.exp` and `StateHeader.ver` in `pqsse/core/state.py`.

**Simplification.** Inside the time window, the cloud could still show the newest note
Bob has already seen instead of an even newer one.

## New data and old searches

**Analogy.** New entries are filed at brand-new secret addresses, so an old search slip
does not point at them.

**Real name.** Forward privacy.

**Code.** The counter `c_w` in `Owner._apply`; measured in
`tests/test_m2_protocol.py::test_forward_privacy_new_updates_share_no_address_with_old_tokens`.

## Deleting

**Analogy.** A delete is one more coded entry that says "cancel document 7". The cloud
cannot tell which earlier entry it cancels.

**Real name.** Type-II backward privacy.

**Code.** `OP_DEL` in `pqsse/core/index.py`, applied in `Receiver._search`.

**Simplification.** The cloud does see that an update happened, when, and how large it
was, and it removes the deleted box.

## Changing the locks

**Analogy.** When a doctor leaves, Alice changes the locks and gives new keys only to
the people still allowed in.

**Real name.** Revocation with epoch rotation. Policy R rotates; policy RE rotates and
re-encrypts.

**Code.** `Owner.revoke`, `Owner._rotate`, `CloudCore._ctl_deauth`,
`CloudCore._ctl_epoch`, `Receiver._accept_rekey`.

**Honest limit.** With policy R, a revoked doctor who colludes with the cloud can still
read data from before the revocation, because it is still locked with the old key.
Policy RE re-locks everything and the cloud drops the old copies. See
`tests/test_m2_revocation.py` and the Attack Lab scenario "Collusion: R vs RE".

## The graphics chip

**Analogy.** A thousand clerks who can each compute one secret address at the same time.

**Real name.** GPU batch engine for HMAC-SHA3-256 and SHA3-256 (CUDA through CuPy).

**Code.** `pqsse/gpu/` (`batchprf.py`, `cuda_kernel.py`, `status.py`).

**Honest limit.** It only speeds up that batch work. ML-KEM and ML-DSA always run on
the normal processor. The app works fully without a GPU.

## The teaching layer

| Piece | Code |
| --- | --- |
| Story text for every event | `pqsse/narrator.py` |
| Narrator panel and diagram | `app/narrator_panel.py`, `app/flow.py` |
| Glossary and tooltips | `app/glossary.py` |
| The 13 lesson steps | `app/lesson.py`, `app/tab_learn.py` |
| "Who sees what" | `app/party_view.py` |
| Challenges | `app/challenges.py` |
| Three-part error messages | `explain_full` in `app/session.py` |
| Attack teaching texts | `TEACH` in `pqsse/attacklab.py` |
