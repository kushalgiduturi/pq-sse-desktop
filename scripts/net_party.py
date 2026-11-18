"""One step of one party (data owner or receiver) for scripts/network_e2e.py, run as its own process.

    python scripts/net_party.py <step> <folder> [json arguments]

Each step opens the party's passphrase-protected vault in <folder>, connects to the server over HTTPS
with the certificate pinned, does one thing, prints one JSON line and exits. Nothing is shared with the
other parties except what a real deployment would share: the server address and fingerprints, the
owner's public key file, the invite file, the one-time code and the receiver's fingerprint words.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pqsse import invite as invites  # noqa: E402
from pqsse.core.errors import Rejected  # noqa: E402
from pqsse.core.keystore import Vault  # noqa: E402
from pqsse.core.pairing import PublicIdentity, export_pub  # noqa: E402
from pqsse.owner import Owner  # noqa: E402
from pqsse.pqbackend import Params  # noqa: E402
from pqsse.receiver import Receiver  # noqa: E402
from pqsse.transport import HttpsCloud  # noqa: E402

PASSPHRASE = "network test passphrase, throwaway"
SCRYPT_N = 2 ** 12          # a throwaway test vault; the app uses the full cost


def vault(folder: Path) -> Vault:
    folder.mkdir(parents=True, exist_ok=True)
    return Vault(folder / "vault.db", PASSPHRASE, scrypt_n=SCRYPT_N)


def cloud(a: dict) -> HttpsCloud:
    return HttpsCloud(a["host"], int(a["port"]), a["pin"], timeout=120)


def main() -> int:
    step, folder = sys.argv[1], Path(sys.argv[2])
    a = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    v = vault(folder)
    out: dict = {}
    try:
        if step == "owner-init":
            api = cloud(a)
            server = PublicIdentity.from_wire(api.call("pub", None))
            if server.fingerprint() != a["server_fp"]:
                raise SystemExit("server key does not match the operator's fingerprint")
            owner = Owner.create(v, Params(a["kem"], a["sig"]), cloud=api)
            owner.pair_cloud(server)
            export_pub(folder / "owner.pqpub", owner.public_identity())
            out = {"owner_fp": owner.public_identity().fingerprint()}
        elif step == "owner-publish":
            owner = Owner(v, cloud=cloud(a))
            owner.create_group("Finance")
            owner.add_document("Finance", "Contract A", "the penalty clause is confidential", ["contract", "confidential"])
            owner.add_document("Finance", "Report Q3", "quarterly report", ["report"])
            owner.publish("Finance")
            inv = owner.create_invite(a["host"], int(a["port"]), a["pin"], "receiver-a")
            (folder / "receiver-a.pqinvite").write_text(inv.to_file(include_code=False), encoding="utf-8")
            out = {"invite_file": str(folder / "receiver-a.pqinvite"), "code": inv.code}
        elif step == "receiver-join":
            inv = invites.parse(Path(a["invite_file"]).read_text(encoding="utf-8"))
            api = HttpsCloud(inv.host, inv.port, inv.tls, timeout=120)
            server = PublicIdentity.from_wire(api.call("pub", None))
            owner = PublicIdentity.from_wire(api.call("owner_pub", None))
            if server.fingerprint() != inv.server_fp or owner.fingerprint() != inv.owner_fp:
                raise SystemExit("a key on the server does not match the invite")
            rec = Receiver.create(v, owner.params, "receiver-a", cloud=api)
            rec.pair(owner, server)
            uid = rec.send_join(inv.id, a["code"])
            out = {"uid": uid, "words": invites.words(rec.public_identity().fingerprint())}
        elif step == "owner-approve":
            owner = Owner(v, cloud=cloud(a))
            [item] = [i for i in owner.pending_joins() if i["uid"] == a["uid"]]
            request = owner.check_join(item)
            if invites.words(request.fingerprint) != a["words"]:
                raise SystemExit("the fingerprint words do not match what the receiver read out")
            owner.approve_join(item, ["Finance"])
            out = {"approved": request.uid, "invite": request.invite_name}
        elif step == "receiver-search":
            rec = Receiver(v, cloud=cloud(a))
            rec.fetch_mail()
            try:
                result = rec.search("Finance", a["word"])
            except Rejected as exc:
                out = {"refused": exc.reason}
            else:
                titles = [rec.open_document("Finance", d, e).title for d, e in result.hits]
                out = {"titles": sorted(titles), "checks_ok": result.report.all_ok, "checks": len(result.report.checks)}
        elif step == "owner-add":
            owner = Owner(v, cloud=cloud(a))
            owner.add_document("Finance", a["title"], a["text"], a["keywords"])
            owner.publish("Finance")
            out = {"added": a["title"]}
        elif step == "owner-revoke":
            owner = Owner(v, cloud=cloud(a))
            owner.revoke(a["uid"], "RE")
            out = {"revoked": a["uid"]}
        else:
            raise SystemExit(f"unknown step {step}")
    finally:
        v.close()
    print(json.dumps(out), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
