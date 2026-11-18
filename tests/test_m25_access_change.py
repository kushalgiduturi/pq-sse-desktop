"""Design note 003: give a receiver more groups, or take some away, without revoking it."""
from __future__ import annotations

import pytest

from pqsse.core import wire
from pqsse.core.errors import AccessDenied, PQSSEError, Rejected, VerifyError
from pqsse.core.prims import group_subkeys
from pqsse.sandbox import World


def setup():
    world = World()
    for g in ("Finance", "Legal"):
        world.owner.create_group(g)
        world.owner.add_document(g, f"{g} doc", f"the {g.lower()} clause", ["clause"])
        world.owner.publish(g)
    dana = world.join("dana", ["Finance"])
    erin = world.join("erin", ["Finance", "Legal"])
    return world, dana, erin


def test_grant_a_group_then_search_it():
    world, dana, erin = setup()
    with pytest.raises(AccessDenied):
        dana.search("Legal", "clause")
    assert world.owner.grant(dana.uid, ["Legal", "Finance"]) == ["Legal"]       # Finance was already there
    assert world.owner.receivers[dana.uid]["groups"] == ["Finance", "Legal"]
    assert dana.fetch_mail() == ["access granted to: Legal"]
    assert len(dana.search("Legal", "clause").hits) == 1
    assert len(dana.search("Finance", "clause").hits) == 1                       # nothing else changed
    assert world.owner.grant(dana.uid, ["Legal"]) == []                          # nothing new: no message at all


def test_take_a_group_away_policy_cut_first_then_keys():
    world, dana, erin = setup()
    old_key = erin._me["cap"]["groups"]["Legal"]["keys"]["1"]
    assert world.owner.take_away(erin.uid, ["Legal"], "R") == ["Legal"]
    with pytest.raises(Rejected) as info:
        erin._request("search", {"g": "Legal", "tok": b"x"})                     # the server refuses the scope at once
    assert info.value.reason == "scope"
    assert len(erin.search("Finance", "clause").hits) == 1                      # the other group still works
    world.owner.add_document("Legal", "after", "a new legal clause", ["clause"])
    world.owner.publish("Legal")
    legal = world.owner.groups["Legal"]
    assert legal["epoch"] == 2 and "2" not in erin._me["cap"]["groups"]["Legal"]["keys"]
    new_doc = world.cloud._load_blob(world.cloud.db.execute("SELECT blob FROM docs WHERE g='Legal' AND e=2").fetchone()[0])
    from pqsse.core.index import doc_aad
    from pqsse.core.prims import aead_decrypt
    aad = doc_aad("Legal", 2, 2)                                                # "after" is document 2 of Legal
    new_key = legal["keys"]["2"]
    assert aead_decrypt(group_subkeys(new_key, "Legal", 2)[1], new_doc, aad)    # the right key opens it ...
    with pytest.raises(VerifyError):                                            # ... the removed receiver's does not
        aead_decrypt(group_subkeys(old_key, "Legal", 2)[1], new_doc, aad)


def test_take_away_with_re_leaves_the_others_reading_everything():
    world, dana, erin = setup()
    world.owner.grant(dana.uid, ["Legal"])
    dana.fetch_mail()
    world.owner.take_away(erin.uid, ["Legal"], "RE")
    dana.fetch_mail()
    result = dana.search("Legal", "clause")
    assert result.report.all_ok and len(result.hits) == 1
    assert world.cloud.db.execute("SELECT MIN(e) FROM docs WHERE g='Legal'").fetchone()[0] == 2   # old segment dropped


def test_a_grant_for_a_revoked_or_unknown_receiver_is_refused_and_an_old_grant_box_adds_nothing():
    world, dana, erin = setup()
    world.owner.revoke(erin.uid, "R")
    with pytest.raises(PQSSEError):
        world.owner.grant(erin.uid, ["Legal"])
    world.owner.grant(dana.uid, ["Legal"])
    [grant] = [m for m in dana.mail_items() if m["kind"] == "grant"]
    dana.fetch_mail()
    before = wire.enc(dana._me["cap"])
    dana._me["mail_done"] = []                                                  # the server replays the old box
    dana.fetch_mail()
    assert wire.enc(dana._me["cap"]) == before
    with pytest.raises(VerifyError):
        dana._accept_grant(grant["body"], b"\x00" * len(grant["sig"]))          # not the owner's signature
    assert world.owner.activity()[0]["what"] == "access.grant"


def test_the_server_refuses_a_scope_change_for_a_receiver_it_does_not_know():
    world, dana, erin = setup()
    world.owner.receivers["ghost"] = dict(world.owner.receivers[dana.uid], name="ghost")
    with pytest.raises(Rejected) as info:
        world.owner.take_away("ghost", ["Finance"])
    assert info.value.reason == "unknown_receiver"


def test_bridge_change_access_and_recover():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.session import Session
    from app.spatial.bridge import AppBridge
    world, dana, erin = setup()
    bridge = AppBridge(Session(), sync=True)
    bridge.session.owner = world.owner
    bridge.changeAccess(dana.uid, ["Legal"], "R")                      # Finance out, Legal in
    assert bridge.activity["note"] == "Access changed. Added: Legal. Taken away: Finance."
    assert world.owner.receivers[dana.uid]["groups"] == ["Legal"]
    assert [r["what"] for r in bridge.activity["rows"]][:2] == ["Groups taken away", "Groups given"]
    bridge.changeAccess(dana.uid, [], "R")
    assert bridge.last_error is not None                                # keep at least one group
    bridge.recoverOwner()
    assert bridge.activity["note"].startswith("Recovery finished: ")
    bridge.session.owner = None
