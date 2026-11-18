"""Design note 006 C: bring a data owner restored from an older backup back in line with the server."""
from __future__ import annotations

import pytest

from pqsse.core.errors import Rejected, VerifyError
from pqsse.core.keystore import MemoryVault
from pqsse.owner import Owner
from pqsse.sandbox import World


def snapshot(owner: Owner) -> MemoryVault:
    """A backup of the owner's vault as it is now."""
    copy = MemoryVault()
    copy._data = dict(owner.vault._data)
    return copy


def restored(world: World, backup: MemoryVault) -> Owner:
    owner = Owner(backup, cloud=world.api, clock=world.clock)
    world.owner = owner
    return owner


def titles(rec, g: str, word: str) -> set[str]:
    rec.fetch_mail()
    result = rec.search(g, word)
    assert result.report.all_ok
    return {rec.open_document(g, d, e).title for d, e in result.hits}


def test_an_old_backup_recovers_documents_keys_and_receivers_made_after_it():
    world = World()
    world.owner.create_group("g")
    world.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    world.owner.publish("g")
    dana = world.join("dana", ["g"])
    backup = snapshot(world.owner)                                  # <- the backup
    world.owner.add_document("g", "Contract B", "a second clause", ["contract"])
    erin = world.join("erin", ["g"])                                # joined after the backup
    frank = world.join("frank", ["g"])
    world.owner.revoke(frank.uid, "R")                              # an epoch change after the backup
    world.owner.add_document("g", "Contract C", "a third clause", ["contract"])
    world.owner.create_group("h")                                   # a group made after the backup
    world.owner.add_document("h", "Memo", "a memo", ["memo"])
    world.owner.publish("g")
    world.owner.publish("h")

    owner = restored(world, backup)
    with pytest.raises(Rejected):                                   # without recovery the server refuses it
        owner.add_document("g", "Too early", "x", ["x"])
    notes = owner.recover()
    assert any(n.startswith("g: rebuilt with 3 document(s)") for n in notes), notes
    assert {d["title"] for d in owner.documents("g")} == {"Contract A", "Contract B", "Contract C"}
    assert {d["title"] for d in owner.documents("h")} == {"Memo"}
    assert set(owner.receivers) == {dana.uid, erin.uid, frank.uid} and owner.receivers[frank.uid]["revoked"]
    assert titles(dana, "g", "contract") == {"Contract A", "Contract B", "Contract C"}
    assert titles(erin, "g", "contract") == {"Contract A", "Contract B", "Contract C"}
    with pytest.raises(Rejected):
        frank.search("g", "contract")
    owner.add_document("g", "Contract D", "after recovery", ["contract"])     # and work goes on
    owner.publish("g")
    assert "Contract D" in titles(erin, "g", "contract")
    assert [e["what"] for e in owner.activity(limit=3)] == ["publish", "doc.add", "recovery"]


def test_a_batch_applied_but_never_published_is_covered_by_the_rebuild():
    world = World()
    world.owner.create_group("g")
    world.owner.publish("g")
    bob = world.join("bob", ["g"])
    backup = snapshot(world.owner)
    world.owner.add_document("g", "Unpublished", "applied at the server, never published", ["contract"])
    owner = restored(world, backup)
    owner.recover()
    assert titles(bob, "g", "contract") == {"Unpublished"}


def test_the_server_can_hide_but_not_forge_documents_during_recovery():
    world = World()
    world.owner.create_group("g")
    for t in ("A", "B"):
        world.owner.add_document("g", f"Contract {t}", "clause", ["contract"])
    world.owner.publish("g")
    backup = snapshot(world.owner)
    real = world.api

    class Hides:
        def call(self, endpoint, obj):
            reply = real.call(endpoint, obj)
            if endpoint == "owner_sync":
                reply["groups"][0]["handles"] = reply["groups"][0]["handles"][:1]
            return reply

    owner = restored(world, backup)
    owner.cloud = Hides()
    owner.recover()
    assert len(owner.documents("g")) == 1                           # hidden: the owner sees less, as receivers would

    class Forges:
        def call(self, endpoint, obj):
            reply = world2.api.call(endpoint, obj)
            if endpoint == "owner_doc":
                reply["blob"] = reply["blob"][:-1] + bytes([reply["blob"][-1] ^ 1])
            return reply

    world2 = World()
    world2.owner.create_group("g")
    world2.owner.add_document("g", "Contract A", "clause", ["contract"])
    backup2 = snapshot(world2.owner)
    owner2 = restored(world2, backup2)
    owner2.cloud = Forges()
    with pytest.raises(VerifyError):
        owner2.recover()


def test_an_owner_from_before_this_change_escrows_its_keys_once():
    world = World()
    world.owner.create_group("g")
    world.owner.add_document("g", "Contract A", "clause", ["contract"])
    world.owner.publish("g")
    bob = world.join("bob", ["g"])
    world.cloud.db.execute("DELETE FROM okeys")                      # as if made before design note 006 C
    world.cloud.db.execute("DELETE FROM orecs")
    world.cloud.db.commit()
    meta = world.owner.vault.get("owner")
    del meta["recovery_key"]
    world.owner.vault.put("owner", meta)
    older = Owner(world.owner.vault, cloud=world.api, clock=world.clock)
    assert older.has_pending
    assert "recovery keys stored at the server" in older.resume_pending()
    assert world.cloud.db.execute("SELECT COUNT(*) FROM okeys").fetchone()[0] == 1
    backup = snapshot(older)
    older.revoke(bob.uid, "R")                                       # epoch 2, escrowed as it happens
    owner = restored(world, backup)
    owner.recover()
    assert owner.receivers[bob.uid]["revoked"] and owner.documents("g")[0]["title"] == "Contract A"


def test_only_the_owner_may_sync_or_fetch_documents_this_way():
    world = World()
    world.owner.create_group("g")
    stranger = Owner.create(MemoryVault(), world.params, cloud=world.api)
    with pytest.raises(Rejected) as info:
        world.api.call("owner_sync", stranger._sync_request("owner_sync", {}))
    assert info.value.reason == "bad_signature"
