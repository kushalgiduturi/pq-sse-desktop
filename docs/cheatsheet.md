# Cheat sheet (2 minutes, printable)

**The idea:** The data owner keeps documents encrypted, yet approved receivers can still search them through the cloud server, and the server learns almost nothing, even against future quantum computers.

**The roles:** Data owner (holds the keys and the documents). Receivers (search only the groups they were
approved for). Cloud server (rented storage, not trusted).

## The ten steps, one sentence each

| # | Name | Who | In plain words |
| --- | --- | --- | --- |
| 1 | **Setup** | Everyone | Each party makes its keys, and they exchange the public halves so they can recognise each other. |
| 2 | **Join** | Receiver A, then the data owner | Receiver A asks to join with a stamped request, and the data owner sends them a sealed access pass with the keys for the groups the owner chooses. |
| 3 | **BuildIndex** | The data owner | The data owner puts each document in a locked box and builds a locked lookup table with one entry per word. |
| 4 | **Update** | The data owner | The data owner adds or deletes documents with numbered, stamped changes that the cloud accepts only once and in order. |
| 5 | **Publish** | The data owner | The data owner publishes a stamped, encrypted summary of the index so receivers can check the cloud's answers. |
| 6 | **TokenGen** | Receiver A | Receiver A turns a word into a sealed search slip that lists secret addresses, not the word. |
| 7 | **Search** | Cloud | The cloud checks Receiver A's permission, fetches what is stored at those addresses, and stamps its answer. |
| 8 | **Verify** | Receiver A | Receiver A's app checks that the answer is genuine, complete, unchanged and recent before showing anything. |
| 9 | **Decrypt** | Receiver A | Receiver A fetches a locked box, checks the data owner's stamp on it, and unlocks it with the group key. |
| 10 | **Revoke** | The data owner | The data owner changes the locks: policy R for new data only, policy RE re-locks everything. |

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
| Capability | Receiver A's access pass: the keys for their groups |
| Credential | Receiver A's secret pass for talking to the cloud |
| Signature | A tamper-proof stamp |
| Epoch | The period in which a group uses one key |
| ML-KEM, ML-DSA | The post-quantum standards for sealing secrets and for stamps |

## Honest limits

- Policy R: a revoked receiver who colludes with the cloud can still read data from before the revocation. Policy RE fixes that, at higher cost.
- The cloud learns sizes, counts, timing and repeated searches. It does not learn words or text.
- The GPU only speeds up building the index. It never speeds up ML-KEM or ML-DSA.
- "Post-quantum" means built on problems believed to be hard for quantum computers. It is not a proof.
- Research software, not audited. Do not protect real data with it.
