# Start here

You do not need to know anything about cryptography to use this app. This page takes
five minutes.

## The idea in one sentence

**Alice keeps her files locked, yet Bob can still search them through the cloud, and the
cloud learns almost nothing, even against future quantum computers.**

## The story

| Who | In the story | In the app |
| --- | --- | --- |
| **Alice** | A hospital records manager | The **Data Owner**. She owns the documents and decides who may read what. |
| **Bob** and **Carol** | Doctors | **Receivers**. They may search and read only the documents Alice allows. |
| **The Cloud** | A rented storage company | Stores everything for Alice, but is **not trusted**: it might peek, lie, drop results or send old data. |

Think of it like this:

- Documents are **letters in locked boxes**.
- A keyword search is **asking the cloud to find boxes without opening them**.
- A search token is **a sealed search slip** only a doctor can make and only the cloud can read.
- A signature is **Alice's tamper-proof stamp**.
- Revocation is **changing the locks** and telling only the people still allowed in.

## The 5-minute guided path

1. Start the app:
   ```powershell
   & "$env:USERPROFILE\.venvs\pqsse\Scripts\python.exe" -m app
   ```
2. On the welcome screen press **Start the guided lesson**.
   (Later you can reopen it with **Help > Welcome screen**, or press **Ctrl+L**.)
3. You are now on the **Learn** tab. Each step has a short explanation and two buttons:
   - **Do it for me** runs the step on the real system.
   - **Let me try** takes you to the right tab and highlights what to press.
4. Read **What just happened** after each step, then press **Next**.
5. Watch the **Narrator** on the right. It says in plain words what each party just did,
   and the small diagram shows what travelled between them.
6. For the full lesson allow about 15 minutes. In a hurry? Do steps 1 to 9, then open the
   page **Who sees what** on the Learn tab and press **Show a document as the cloud sees it**.

The lesson uses its own practice area. Every passphrase there is the word `lesson`.
Your own data is never touched, and **Reset lesson** gives you a clean start.

## After the lesson you can answer

- **What does Alice do?** She locks her documents, builds a locked index, stamps
  everything she sends, and decides who gets which key.
- **What does Bob do?** He sends a sealed search slip, checks the cloud's answer against
  what Alice stamped, and only then unlocks the documents he is allowed to read.
- **What does the Cloud see?** Locked bytes, sizes, counts, timing, and which secret
  addresses are asked for. No words, no titles, no text, no keys.
- **Why can the cloud not read the data?** It never receives a group key. Without the
  key, a locked box is just random-looking bytes.
- **What happens when someone is revoked?** The cloud stops accepting their pass, the
  group gets a new key, and only the doctors who stay receive it.
- **What if the cloud cheats?** A check fails on Bob's side and nothing is shown. The
  Attack Lab lets you watch that happen.

## Questions people ask

**Is this safe?**
The main security claims are exercised by automated tests, including a cloud that cheats
on purpose. But this is research software. It has not been audited by outside experts, and the post-quantum code it uses
by default is a slow teaching version. Do not use it to protect real records.

**Is it really quantum-proof?**
Nobody can honestly say "proof". The app uses ML-KEM and ML-DSA, two standards that were
designed to resist quantum computers and were studied publicly for years. They rest on
math problems that are *believed* to be hard for quantum computers too. That is the
state of the art, not a guarantee.

**Why do I need a GPU?**
You do not. The app works fully without one and gives the same results. A graphics chip
only speeds up one thing: computing the many secret addresses when Alice builds a large
index. It does **not** speed up the post-quantum steps (ML-KEM and ML-DSA), which always
run on the normal processor. For small amounts of data the GPU is not faster at all, and
the Benchmarks tab shows the measured numbers honestly.

**What does the cloud actually know?**
More than nothing, and it is worth being precise:
- how many documents and index entries exist, and how big they are;
- group names, how many doctors exist and which groups each may ask about;
- when requests happen, and whether the same search was made before (the same addresses
  are asked for again), and how many entries matched;
- that an update happened and how large it was.

It does not know the search words, the documents, their titles, or any key.

**What is the catch with revocation?**
There are two ways to revoke. **Policy R** changes the key for everything written from
now on. It is quick, but data from before the change is still locked with the old key.
A revoked doctor who teams up with the cloud can still read that older data.
**Policy RE** also re-locks every existing document, which closes that gap but takes
longer. Neither can take back what a doctor already downloaded or remembers.

**I only see technical words. Where is the plain version?**
Switch on **Beginner Mode** in the toolbar. Hover over any underlined or technical word
for a one-sentence meaning, or press **F1** for the glossary.

## Where to go next

- [cheatsheet.md](cheatsheet.md): the ten steps of the system, one sentence each.
- [concepts.md](concepts.md): each idea with its analogy, its real name and where it lives in the code.
- The **Challenges** page on the Learn tab: seven short tasks, no score, hints included.
- The **Attack Lab** tab: eleven attacks, each shown being caught.
- [architecture.md](architecture.md) and [wire-format.md](wire-format.md): for readers who want every detail.
