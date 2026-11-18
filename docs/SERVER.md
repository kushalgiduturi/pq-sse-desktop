# Running the PQ-SSE cloud server

The cloud server (`pqsse-server`) stores the encrypted index, the encrypted documents and the signed
states, checks every request, and answers searches. It never holds a group key, so it cannot read
documents or search words: everything it stores is ciphertext, masked index entries and public keys.
This guide is for the person who runs it (the operator).

Status: milestone 2 of `REALLIFE_PLAN.md`. The server runs and is tested on this PC (Windows 11, from
source and as the console exe). **Not yet verified:** the Docker image (built from `docker/Dockerfile`,
never run here because Docker was not running), a server on another machine, use over the internet.
The desktop app cannot use this server yet: the client modes and invites arrive in milestone 3.

## Install

| Where | How |
| --- | --- |
| Windows, from source | `python -m pip install -r requirements-server.txt`, then `python -m pqsse.server ...` |
| Windows, console program | `.\build_server.ps1` builds `pqsse-server.exe` (one folder, about 60 MB) and smoke-tests it |
| Linux, Docker | `docker compose -f docker/docker-compose.yml up -d` (see the comments in that file) |

## First start

```powershell
python -m pqsse.server init --config pqsse-server.toml     # writes a configuration template
# edit pqsse-server.toml: public_names (how clients reach this machine) and passphrase_file
python -m pqsse.server init --config pqsse-server.toml     # makes keys, certificate and admin token
python -m pqsse.server pair-owner owner.pqpub --config pqsse-server.toml
python -m pqsse.server run --config pqsse-server.toml
```

`init` prints two fingerprints: the **TLS certificate** (clients pin it) and the **server key** (the
data owner and receivers compare it). Both go into invites in milestone 3; until then give them to the
data owner over a channel you trust.

The passphrase protects the server's ML-KEM and ML-DSA keys and the receivers' credentials at rest. It
is read from `passphrase_file`, from the Docker secret `pqsse_passphrase`, or from a prompt, and never
from the command line. If it is lost, the store cannot be opened and the data owner must set up again.

## Configuration

One TOML file; every setting can also be given as `PQSSE_SERVER_<NAME>` (environment variables win).

| Setting | Default | Meaning |
| --- | --- | --- |
| `data_dir` | `pqsse-server-data` | store, document files, certificate, admin token |
| `host`, `port` | `0.0.0.0`, `8443` | the public HTTPS API |
| `admin_host`, `admin_port` | `127.0.0.1`, `8444` | the operator interface; refuses other addresses unless `allow_remote_admin = true` |
| `public_names` | `localhost`, `127.0.0.1` | names and addresses in the self-signed certificate |
| `tls_cert`, `tls_key` | empty | your own certificate instead of the self-signed one (clients still pin it) |
| `passphrase_file` | empty | file with the passphrase |
| `kem`, `sig` | `ML-KEM-768`, `ML-DSA-65` | used when the store is new; must match the data owner's |
| `max_body_bytes` / `max_small_body_bytes` | 64 MiB / 4 MiB | request size for update and state uploads / everything else |
| `max_doc_bytes`, `max_docs_per_group`, `max_storage_bytes` | 16 MiB, 100,000, 10 GiB | storage limits |
| `requests_per_minute` | 600 | per client address and per receiver credential |
| `max_connections`, `request_deadline` | 64, 60 s | open connections; total time a connection may take (slow clients are cut) |

## What it protects, and how

- **TLS**: TLS 1.2 or 1.3 only; for TLS 1.2 only ECDHE with AES-GCM or ChaCha20-Poly1305; no
  compression or renegotiation. The certificate is self-signed (ECDSA P-256) unless you supply one;
  clients pin its SHA-256 fingerprint and refuse any other certificate before sending a byte. TLS uses
  classical key exchange: the post-quantum protection of keys and data comes from the protocol inside it.
- **API**: `POST /v1/<endpoint>` with the canonical wire encoding (`docs/wire-format.md`); `GET /v1/time`
  for the clients' clock check. Operator endpoints are not on this port. Error replies carry a short
  reason and never a stack trace, key or path.
- **Abuse limits**: body size per endpoint (413), requests per minute (429 with `Retry-After`), open
  connections (503), a total deadline per connection that also ends slow TLS handshakes.
- **Storage**: SQLite in WAL mode with full sync; documents as files named by their SHA-256, written
  atomically; a quick integrity check at every start; the store refuses to start when damaged.

## Operating it

```powershell
python -m pqsse.server admin status                 # version, backend, pairing, fingerprint, connections
python -m pqsse.server admin storage                # bytes used, limit, documents, entries, groups
python -m pqsse.server admin connections            # open connections: address, seconds, endpoint
python -m pqsse.server admin log                    # last requests: endpoint, sizes, accepted or refused
python -m pqsse.server admin rotate-token           # new admin token (the old one stops working)
python -m pqsse.server admin backup [DEST]          # consistent copy while running
python -m pqsse.server admin delete-group GROUP     # remove every stored item of a group
python -m pqsse.server check                        # verify the store without starting (no passphrase needed)
python -m pqsse.server backup DEST                  # the same backup, without the admin interface
python -m pqsse.server restore SOURCE               # into an empty data folder
```

The admin commands read the token from `data_dir/admin.token` and talk to `127.0.0.1:admin_port`.
Nothing the operator interface returns contains a key, a passphrase or document text: the tests check
this by searching every admin reply for the plaintext words of the test documents.

## Backups

A backup is a folder with the database (SQLite online backup) and the document files it refers to, plus
`pqsse-backup.json`. It is checked after it is written. Restore copies it into an empty data folder; a
new TLS certificate and admin token are made at the next start, so clients need the new certificate
fingerprint (the server's own keys, and so its key fingerprint, are restored unchanged).
