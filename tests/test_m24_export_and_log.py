"""Design notes 006 A (group export and import) and 007 (the data owner's activity log)."""
from __future__ import annotations

import csv

import pytest

from pqsse.core import fileperm, wire
from pqsse.core.errors import BadPassphrase, PQSSEError, Rejected
from pqsse.core.keystore import Vault, import_backup
from pqsse.owner import DocInput, Owner
from pqsse.owner import owner as owner_module
from pqsse.pqbackend import FAST_PARAMS
from pqsse.sandbox import World


# ------------------------------------------------------------------ 006 A: export and import
def test_export_and_import_a_group_into_another_installation(tmp_path, monkeypatch):
    monkeypatch.setattr(owner_module, "BATCH_DOCS", 4)
    first = World()
    first.owner.create_group("Finance")
    first.owner.build_index("Finance", [DocInput(f"Invoice {i}", f"invoice number {i}", ["invoice", f"n{i}"]) for i in range(9)])
    first.owner.delete_document("Finance", 3)
    with pytest.raises(PQSSEError):
        first.owner.export_group("Finance", tmp_path / "short.pqgroup", "too short")
    path = first.owner.export_group("Finance", tmp_path / "finance.pqgroup", "an export passphrase")
    raw = path.read_bytes()
    assert b"Invoice" not in raw and b"invoice" not in raw and fileperm.is_private(path)[0]
    with pytest.raises(PQSSEError):
        first.owner.export_group("Finance", path, "an export passphrase")          # never overwrites

    second = World()                                                               # another owner, another cloud
    with pytest.raises(BadPassphrase):
        second.owner.import_group(path, "the wrong passphrase")
    damaged = tmp_path / "damaged.pqgroup"
    damaged.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(BadPassphrase):
        second.owner.import_group(damaged, "an export passphrase")
    with pytest.raises(PQSSEError):
        second.owner.import_group(tmp_path / "finance.pqgroup", "an export passphrase", g="x" * 65)   # bad name
    group, ids = second.owner.import_group(path, "an export passphrase", g="Finance 2026")
    assert group == "Finance 2026" and len(ids) == 8 and second.owner.groups[group]["seq"] == 2   # split: 4 + 4
    second.owner.publish(group)
    bob = second.join("receiver-a", [group])
    titles = {bob.open_document(group, d, e).title for d, e in bob.search(group, "invoice").hits}
    assert titles == {f"Invoice {i}" for i in range(9) if i != 2}                  # ids start at 1: id 3 is Invoice 2


def test_a_key_backup_never_carries_a_journal_record(tmp_path):
    vault = Vault(tmp_path / "o.sqlite", "owner passphrase", 2 ** 12)
    vault.put("owner", {"x": 1})
    vault.put("journal:ctl", {"endpoint": "ctl"})
    backup = vault.export_backup(tmp_path / "o.pqkeys", "a long backup passphrase", scrypt_n=2 ** 12)
    restored = import_backup(backup, "a long backup passphrase", tmp_path / "r.sqlite", "new passphrase", 2 ** 12)
    assert list(restored.names("journal:")) == [] and restored.get("owner") == {"x": 1}
    vault.close()
    restored.close()


# ------------------------------------------------------------------ 007: the activity log
def test_every_owner_action_writes_one_entry_with_the_servers_answer():
    world = World()
    owner = world.owner
    owner.create_group("g")
    owner.build_index("g", [DocInput("Contract A", "the penalty clause", ["contract"]),
                            DocInput("Contract B", "the other clause", ["contract"])])
    owner.edit_document("g", 1, "Contract A, signed", "the penalty clause, signed")
    owner.delete_document("g", 2)
    owner.publish("g")
    bob = world.join("receiver-a", ["g"])
    inv = owner.create_invite("127.0.0.1", 1, "ab" * 32, "dana")
    owner.revoke(bob.uid, "RE")
    world.cloud.db.execute("UPDATE groups SET seq = 99 WHERE g='g'")                  # the next batch is refused
    world.cloud.db.commit()
    with pytest.raises(Rejected):
        owner.add_document("g", "Refused", "x", ["x"])
    whats = [e["what"] for e in reversed(owner.activity())]
    assert whats == ["group.create", "doc.add", "doc.edit", "doc.delete", "publish", "join.approve", "invite.create",
                     "revoke", "doc.add"]                     # the revocation's own publishes are not separate entries
    last = owner.activity(limit=1)[0]
    assert last["server"] == "bad_sequence" and last["detail"]["title"] == "Refused"
    approve = owner.activity(receiver="receiver-a")
    assert {e["what"] for e in approve} == {"join.approve", "revoke"}
    assert approve[-1]["detail"]["fingerprint"] and approve[0]["detail"]["policy"] == "RE"
    assert [e["what"] for e in owner.activity(group="g")][:1] == ["doc.add"]
    assert inv.code not in repr(owner.activity())                                     # the one-time code is never logged
    assert owner.verify_activity() == (True, "9 entries, chain intact")


def test_the_chain_detects_a_deleted_an_edited_and_a_swapped_entry():
    for damage in ("delete", "edit", "swap"):
        world = World()
        owner = world.owner
        for g in ("a", "b", "c"):
            owner.create_group(g)
        names = sorted(owner.vault.names("log:"))
        if damage == "delete":
            owner.vault.delete(names[1])
        elif damage == "edit":                                 # re-encrypted with the right key, so the vault accepts it
            entry = owner.vault.get(names[1])
            entry["detail"] = {"group": "something else"}
            owner.vault.put(names[1], entry)
        else:
            one, two = owner.vault.get(names[0]), owner.vault.get(names[1])
            owner.vault.put(names[0], two)
            owner.vault.put(names[1], one)
        ok, why = owner.verify_activity()
        assert not ok and why, damage


def test_the_log_survives_a_passphrase_change_and_a_backup_and_exports_to_csv(tmp_path):
    world = World()
    vault = Vault(tmp_path / "owner.sqlite", "owner passphrase", 2 ** 12)
    owner = Owner.create(vault, FAST_PARAMS, cloud=world.api, clock=world.clock)
    owner.pair_cloud(world.cloud.public_identity())
    world.cloud.pair_owner(owner.public_identity(), replace=True)
    owner.create_group("g")
    owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    vault.change_passphrase("owner passphrase", "a new owner passphrase")
    backup = vault.export_backup(tmp_path / "owner.pqkeys", "a long backup passphrase", scrypt_n=2 ** 12)
    restored = Owner(import_backup(backup, "a long backup passphrase", tmp_path / "r.sqlite", "restored pass", 2 ** 12))
    assert restored.verify_activity() == (True, "2 entries, chain intact")   # the group's first publish is part of its creation
    out = owner.export_activity_csv(tmp_path / "activity.csv")
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[0] == ["n", "time_utc", "what", "server", "detail"] and [r[2] for r in rows[1:]] == ["group.create", "doc.add"]
    assert "title=Contract A" in rows[2][4]
    restored.vault.close()
    vault.close()


def test_log_details_are_wire_safe():
    assert wire.dec(wire.enc(owner_module._plain({"a": None, "b": 1.5, "c": True, "d": {1, 2}, "e": object}))) is not None


# ------------------------------------------------------------------ the app
def test_bridge_export_import_and_activity(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.session import Session
    from app.spatial.bridge import AppBridge
    bridge = AppBridge(Session(), sync=True)
    session = bridge.session
    session.settings["kem"], session.settings["sig"] = FAST_PARAMS.kem, FAST_PARAMS.sig
    world = World()
    session.owner = Owner.create(Vault(tmp_path / "o.sqlite", "owner passphrase", 2 ** 12), FAST_PARAMS, cloud=world.api)
    session.owner.pair_cloud(world.cloud.public_identity())
    world.cloud.pair_owner(session.owner.public_identity(), replace=True)
    session.owner.create_group("Finance")
    session.owner.add_document("Finance", "Invoice 1", "invoice one", ["invoice"])
    bridge.exportGroup("Finance", "an export passphrase")
    note = bridge.activity["note"]
    assert note.startswith("Exported to ") and ".pqgroup" in note
    path = note[len("Exported to "):].split(". Keep")[0]
    bridge.importGroup(path, "an export passphrase", "Finance copy")
    assert bridge.activity["note"] == "Imported 1 documents into Finance copy and published."
    rows = bridge.activity["rows"]
    assert [r["what"] for r in rows][:5] == ["Published", "Documents imported", "Group exported", "Documents added", "Group created"]
    assert bridge.activity["ok"] and "chain intact" in bridge.activity["check"]
    bridge.exportActivity()
    assert bridge.activity["note"].startswith("Activity written to ")
    session.owner.vault.close()
    session.owner = None
    assert bridge.activity["open"] is False
