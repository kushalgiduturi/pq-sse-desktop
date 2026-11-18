"""Milestone 5 of REALLIFE_PLAN.md: the key lifecycle.

Change passphrase, encrypted key backup and import, private file permissions for key files, overwriting the
master key on close, auto-lock in the app, and the server's key files.
"""
from __future__ import annotations

import sqlite3

import pytest
from test_m16_server import Running

from pqsse.core import fileperm
from pqsse.core.errors import BadPassphrase, PQSSEError
from pqsse.core.keystore import Vault, import_backup
from pqsse.owner import Owner
from pqsse.pqbackend import FAST_PARAMS
from pqsse.receiver import Receiver
from pqsse.sandbox import World

N = 2 ** 12          # a cheap scrypt cost for throwaway test vaults


def all_bytes(path) -> bytes:
    return b"".join(p.read_bytes() for p in path.parent.glob(path.name + "*"))


# ------------------------------------------------------------------ the vault
def test_change_passphrase_re_encrypts_everything_and_keeps_the_keys(tmp_path):
    path = tmp_path / "owner.sqlite"
    vault = Vault(path, "old passphrase", N)
    owner = Owner.create(vault, FAST_PARAMS)
    vault.put("group:g", {"note": "a second record"})
    before = {n: vault.get(n) for n in vault.names()}
    blobs_before = dict(sqlite3.connect(path).execute("SELECT name, blob FROM vault").fetchall())
    with pytest.raises(BadPassphrase):
        vault.change_passphrase("wrong", "new passphrase")
    vault.change_passphrase("old passphrase", "new passphrase")
    assert {n: vault.get(n) for n in vault.names()} == before            # still usable without reopening
    blobs_after = dict(sqlite3.connect(path).execute("SELECT name, blob FROM vault").fetchall())
    assert all(blobs_before[n] != blobs_after[n] for n in blobs_before)  # every record rewritten
    vault.close()
    with pytest.raises(BadPassphrase):
        Vault(path, "old passphrase", N)
    again = Vault(path, "new passphrase", N)
    assert Owner(again).vk == owner.vk
    again.close()


def test_a_failed_passphrase_change_leaves_the_old_passphrase_working(tmp_path, monkeypatch):
    path = tmp_path / "r.sqlite"
    vault = Vault(path, "old passphrase", N)
    Receiver.create(vault, FAST_PARAMS, "dana")
    from pqsse.core import keystore
    calls = {"n": 0}
    real = keystore.aead_encrypt

    def fails_half_way(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk went away")
        return real(*args, **kwargs)

    monkeypatch.setattr(keystore, "aead_encrypt", fails_half_way)
    with pytest.raises(OSError):
        vault.change_passphrase("old passphrase", "new passphrase")
    monkeypatch.setattr(keystore, "aead_encrypt", real)
    assert vault.get("receiver")["name"] == "dana"
    vault.close()
    reopened = Vault(path, "old passphrase", N)
    assert reopened.get("receiver")["name"] == "dana"
    reopened.close()


def test_backup_round_trip_wrong_passphrase_tampering_and_no_overwrite(tmp_path):
    world = World()
    world.owner.create_group("g")
    world.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    src = Vault(tmp_path / "rec.sqlite", "receiver passphrase", N)
    rec = Receiver.create(src, FAST_PARAMS, "dana", cloud=world.api)
    rec.pair(world.owner.public_identity(), world.cloud.public_identity())
    uid = rec.send_join()
    world.owner.approve_join(next(i for i in world.owner.pending_joins() if i["uid"] == uid), ["g"])
    rec.fetch_mail()
    world.owner.publish("g")
    with pytest.raises(PQSSEError):
        src.export_backup(tmp_path / "short.pqkeys", "too short")
    backup = src.export_backup(tmp_path / "dana.pqkeys", "a long backup passphrase", scrypt_n=N)
    with pytest.raises(PQSSEError):
        src.export_backup(backup, "a long backup passphrase", scrypt_n=N)            # never overwrites
    raw = backup.read_bytes()
    assert rec._dk not in raw and rec._sk not in raw and b"dana" not in raw            # sealed, names included
    assert fileperm.is_private(backup)[0]

    with pytest.raises(BadPassphrase):
        import_backup(backup, "the wrong passphrase", tmp_path / "x.sqlite", "new pass", N)
    damaged = tmp_path / "damaged.pqkeys"
    damaged.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(BadPassphrase):
        import_backup(damaged, "a long backup passphrase", tmp_path / "y.sqlite", "new pass", N)
    with pytest.raises(PQSSEError):
        import_backup(backup, "a long backup passphrase", tmp_path / "rec.sqlite", "new pass", N)   # exists

    restored = Receiver(import_backup(backup, "a long backup passphrase", tmp_path / "restored.sqlite",
                                      "another passphrase", N), cloud=world.api)
    assert restored.uid == rec.uid
    assert len(restored.search("g", "contract").hits) == 1                       # the restored keys work
    restored.vault.close()
    src.close()


def test_new_vaults_are_private_and_closing_overwrites_the_master_key(tmp_path):
    vault = Vault(tmp_path / "k.sqlite", "passphrase", N)
    assert fileperm.is_private(tmp_path / "k.sqlite") == (True, "")
    master = vault._master
    assert any(master)
    vault.close()
    assert not any(master)


def test_a_wrong_passphrase_leaves_no_master_key_behind(tmp_path, monkeypatch):
    Vault(tmp_path / "k.sqlite", "right", N).close()
    seen = []
    real = Vault._wipe
    monkeypatch.setattr(Vault, "_wipe", lambda self: (seen.append(self._master), real(self)))
    with pytest.raises(BadPassphrase):
        Vault(tmp_path / "k.sqlite", "wrong", N)
    assert seen and not any(seen[0])


# ------------------------------------------------------------------ the server's key files
def test_server_key_files_are_private(tmp_path):
    running = Running(tmp_path)
    try:
        for path in (running.config.store_path, running.config.data_dir / "server.key", running.config.admin_token_path):
            assert fileperm.is_private(path) == (True, ""), path
        assert fileperm.is_private(running.config.data_dir)[0]
    finally:
        running.close()


# ------------------------------------------------------------------ the app
def test_session_change_backup_import_and_lock(tmp_path):
    from app.session import Session
    session = Session()
    session.settings["kem"], session.settings["sig"] = FAST_PARAMS.kem, FAST_PARAMS.sig
    session.open_owner("owner passphrase")
    vk = session.owner.vk
    with pytest.raises(PQSSEError):
        session.change_passphrase("owner", "owner passphrase", "short")
    session.change_passphrase("owner", "owner passphrase", "a new owner passphrase")
    backup = session.backup_keys("owner", "backup passphrase, long")
    assert session.lock_keys() == ["owner"] and session.owner is None and session.keys_open() == []
    with pytest.raises(BadPassphrase):
        session.open_owner("owner passphrase")
    session.open_owner("a new owner passphrase")
    assert session.owner.vk == vk
    with pytest.raises(PQSSEError):
        session.import_keys(backup, "backup passphrase, long", "restored passphrase")     # keys exist here
    session.lock_keys()
    from pqsse import paths
    paths.owner_db().unlink()                                                             # as on a new computer
    assert session.import_keys(backup, "backup passphrase, long", "restored passphrase") == "owner"
    session.open_owner("restored passphrase")
    assert session.owner.vk == vk
    session.close()


def test_bridge_auto_lock(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.session import Session
    from app.spatial import bridge as bridge_module
    bridge = bridge_module.AppBridge(Session(), sync=True)
    bridge.session.settings["kem"], bridge.session.settings["sig"] = FAST_PARAMS.kem, FAST_PARAMS.sig
    bridge.session.open_owner("owner passphrase")
    assert bridge.keys["open"] == ["owner"] and bridge.keys["autolock"] == 15
    bridge.autolockTick()
    assert bridge.keys["open"] == ["owner"]                    # not idle long enough
    clock = [bridge._last_action + 15 * 60 + 1]
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: clock[0])
    bridge.setAutolock(0)
    bridge.autolockTick()
    assert bridge.keys["open"] == ["owner"]                    # 0 turns auto-lock off
    bridge.setAutolock(15)
    bridge.autolockTick()
    assert bridge.keys["open"] == [] and "15 minutes" in bridge.keys["note"]
    assert bridge.keys["backend"] and bridge.keys["coverage"]
    bridge.session.close()
