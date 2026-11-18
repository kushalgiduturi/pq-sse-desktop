# Trying PQ-SSE on separate machines

This is the stop at the end of milestone 4 of `REALLIFE_PLAN.md`. Everything below has passed on one
computer: loopback, separate processes and Docker. It has **not** yet been run across a real network.
That is what this page is for.

You need two or three Windows PCs (or VMs) on the same private network:

| Machine | Runs | Can share a PC with |
| --- | --- | --- |
| **S**, the server | `python -m pqsse.server` | the owner, if you only have two machines |
| **O**, the data owner | the app in Data owner mode (or `scripts/net_party.py`) | the server |
| **R**, the receiver | the app in Receiver mode (or `scripts/net_party.py`) | nothing: use a different PC from O |

Nothing here opens a port to the internet. The server listens on your private network only, and only
after **you** add the firewall rule in step 2. Remove that rule when you are done (step 7).

## 1. Copy the code to each machine

The `reallife` branch is not pushed. On this PC, make a source archive:

```powershell
git -C C:\Users\Kushal\pqsse-reallife archive -o C:\Users\Kushal\pqsse-reallife.zip reallife
```

Copy `pqsse-reallife.zip` to each machine, for example by USB stick or a shared folder. Unpack it to a
folder outside OneDrive. Then, in that folder:

```powershell
py -3.11 -m venv .venv
```

```powershell
.venv\Scripts\python -m pip install -r requirements-lock.txt
```

On S alone, `requirements-server.txt` is enough. It needs no Qt.

## 2. Server machine S

Find S's private address with `ipconfig` (for example `192.168.1.20`). Then:

```powershell
.venv\Scripts\python -m pqsse.server init --config server.toml
```

Edit `server.toml`:

- set `public_names = ["192.168.1.20"]` (S's address)
- set `passphrase_file` to a file that holds a long passphrase, readable by your account only

Run `init` again, then start the server:

```powershell
.venv\Scripts\python -m pqsse.server init --config server.toml
```

```powershell
.venv\Scripts\python -m pqsse.server run --config server.toml
```

Note the two fingerprints that `init` printed: the **TLS certificate SHA-256** and the **Server key fingerprint**.

Allow the port on the **Private** network profile only. Run this in an administrator PowerShell.
It is your decision, and you can remove the rule again in step 7:

```powershell
New-NetFirewallRule -DisplayName "PQSSE test 8443" -Direction Inbound -Protocol TCP -LocalPort 8443 -Profile Private -Action Allow
```

The operator port (8444) stays on 127.0.0.1 and must not be opened.

## 3. Data owner machine O (the app)

1. Start the app. On the welcome sheet, choose **Data owner**.
2. In Workspace, Cloud server, enter S's address, port 8443, the TLS fingerprint and the server key
   fingerprint from step 2. Then press Connect.
   - Expected: "Connected". A wrong fingerprint must be refused before anything is sent.
3. Create the data owner's keys. Copy the file `owner.pqpub` to S: open Insights, Data and logs, Open
   data folder, then `network\pubkeys`. On S, install it with:

```powershell
.venv\Scripts\python -m pqsse.server pair-owner owner.pqpub --config server.toml
```

4. Create a group, add a few documents, publish.
5. Invite a person: type a name, then Make an invite. Send the `.pqinvite` file (or the link) to R by
   one channel. Send the one-time code by **another** channel, such as a phone call or a message.

## 4. Receiver machine R (the app)

1. Start the app. Choose **Receiver**.
2. Join with an invite: paste the link or the file contents, enter the code, your name and a passphrase.
   - Expected: the app checks the server certificate and both public keys against the invite before
     it sends anything. It then shows six fingerprint words.
3. Read the six words to the data owner, for example on the phone.

## 5. Back on O

The join request appears with the same six words and "with the invite for <name>". Approve it only if
the words match, and choose the group.

## 6. On R: search and open

Press Fetch mailbox, then search a keyword from step 3.4 and open the document. The verification panel should
show every check passed.

### Things worth trying while you are there

| Try | Expected |
| --- | --- |
| Unplug R's network during a search, plug it back in, search again | a clear "not reachable" message, then normal results, with nothing lost |
| Stop the server on S (Ctrl+C) and start it again | same results afterwards, same fingerprints |
| Use the same invite again from another PC | refused: "this invite was already used" |
| Enter a wrong code | refused: "the invite code does not match" |
| Set R's clock 10 minutes wrong, then Connect | refused: the clock is more than about 5 minutes off (a warning from 2 minutes) |
| On O, revoke R with policy RE | R's next search is refused as revoked |
| From R, open `http://192.168.1.20:8444/admin/status` in a browser | no answer (the operator port is local to S) |
| On S: `python -m pqsse.server admin status --config server.toml` | counts and sizes only, with no keywords, titles or text |

## 7. Clean up

On S, in an administrator PowerShell:

```powershell
Remove-NetFirewallRule -DisplayName "PQSSE test 8443"
```

Then delete the unpacked folders and the server data folder if you do not need them.

## Without the app: the scripted run

`scripts/net_party.py` runs one step of the owner or the receiver as its own process. It is the same
code that `scripts/network_e2e.py` drives on one PC. To run it across machines, follow
`scripts/network_e2e.py` by hand: `owner-init` and `owner-publish` on O, `pair-owner` on S, `receiver-join`
on R, `owner-approve` on O, `receiver-search` on R. Each step prints one JSON line. Pass
`{"host": "192.168.1.20", "port": 8443, "pin": "<TLS fingerprint without spaces>"}` as the network arguments.

## What to send back to me

For each row that did not behave as described: the step, what you saw (a screenshot without
passphrases or codes), and the server's console output around that time. The server never prints keys
or document contents. Do not send the passphrase file, the vaults or the `.pqinvite` code.
