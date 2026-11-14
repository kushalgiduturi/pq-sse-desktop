# Cheat sheet (2 minutes, printable)

**The idea:** Alice keeps her files locked, yet Bob can still search them through the
cloud, and the cloud learns almost nothing, even against future quantum computers.

**Who is who:** Alice = data owner (hospital records manager). Bob, Carol = receivers
(doctors). Cloud = rented storage, not trusted.

## The ten steps, one sentence each

| # | Name | Who | In plain words |
| --- | --- | --- | --- |
| 1 | **Setup** | Everyone | Each party makes its keys, and they exchange the public halves so they can recognise each other. |
| 2 | **Join** | Bob, then Alice | Bob asks to join with a stamped request, and Alice sends him a sealed access pass with the keys for the groups she chooses. |
| 3 | **BuildIndex** | Alice | Alice puts each document in a locked box and builds a locked lookup table with one entry per word. |
| 4 | **Update** | Alice | Alice adds or deletes documents with numbered, stamped changes that the cloud accepts only once and in order. |
| 5 | **Publish** | Alice | Alice publishes a stamped, encrypted summary of the index so doctors can check the cloud's answers. |
| 6 | **TokenGen** | Bob | Bob turns a word into a sealed search slip that lists secret addresses, not the word. |
| 7 | **Search** | Cloud | The cloud checks Bob's permission, fetches what is stored at those addresses, and stamps its answer. |
| 8 | **Verify** | Bob | Bob's app checks that the answer is genuine, complete, unchanged and recent before showing anything. |
| 9 | **Decrypt** | Bob | Bob fetches a locked box, checks Alice's stamp on it, and unlocks it with the group key. |
| 10 | **Revoke** | Alice | Alice changes the locks: policy R for new data only, policy RE re-locks everything. |

## The eight checks in Verify (step 8)

| Check | Stops the cloud from |
| --- | --- |
| State signature | inventing what the index contains |
| Segments complete | hiding a whole part of the index |
| Older segments final | slipping entries into closed parts |
| Freshness | serving an expired summary |
| No rollback | going back to an older version |
| Response signature | denying or reusing an answer |
| Completeness | dropping, adding or reordering results |
| Hash chain | changing or swapping a result |

## Words

| Word | Meaning |
| --- | --- |
| Ciphertext | Locked data that looks like random bytes |
| Token | The sealed search slip |
| Capability | Bob's access pass: the keys for his groups |
| Credential | Bob's secret pass for talking to the cloud |
| Signature | A tamper-proof stamp |
| Epoch | The period in which a group uses one key |
| ML-KEM, ML-DSA | The post-quantum standards for sealing secrets and for stamps |

## Honest limits

- Policy R: a revoked doctor who colludes with the cloud can still read data from before the revocation. Policy RE fixes that, at higher cost.
- The cloud learns sizes, counts, timing and repeated searches. It does not learn words or text.
- The GPU only speeds up building the index. It never speeds up ML-KEM or ML-DSA.
- "Post-quantum" means built on problems believed to be hard for quantum computers. It is not a proof.
- Research software, not audited. Do not protect real data with it.
