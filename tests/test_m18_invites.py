"""Design note 002 (approved): invites, the checked network join, closed endpoints, documents in parts."""
from __future__ import annotations

import pytest
from test_m16_server import FAST, Running

from pqsse import invite as invites
from pqsse.core import wire
from pqsse.core.errors import Rejected, VerifyError
from pqsse.core.keystore import MemoryVault
from pqsse.core.pairing import PublicIdentity
from pqsse.owner import DocInput, Owner
from pqsse.receiver import Receiver
from pqsse.receiver import receiver as receiver_module
from pqsse.sandbox import World
from pqsse.transport import CloudUnavailable, HttpsCloud


# ------------------------------------------------------------------ the invite itself
def test_invite_file_and_link_round_trip_and_the_code_stays_out_of_the_file():
    inv = invites.new_invite("pq.example.org", 8443, "ab" * 32, "8EC9 8B55 59FC", "1A2B 3C4D", "dana")
    assert "-" in inv.code and len(invites.normalise_code(inv.code)) == 12
    from_file = invites.parse(inv.to_file())
    assert from_file.code == "" and from_file.id == inv.id and from_file.host == "pq.example.org"
    from_link = invites.parse(inv.to_link(include_code=True))
    assert from_link.code == inv.code and from_link.port == 8443 and from_link.tls == "ab" * 32
    for bad in ("hello", '{"v": 9}', "pqsse://h:1/join?v=1"):
        with pytest.raises(invites.InviteError):
            invites.parse(bad)


def test_fingerprint_words_are_stable_and_use_256_distinct_words():
    assert len(invites.WORDS) == 256 and len(set(invites.WORDS)) == 256
    assert invites.words("00 01 02 03 04 05 ff") == " ".join(invites.WORDS[:6])
    assert invites.words("8EC9 8B55 59FC 3934") == invites.words("8ec98b5559fc3934")


# ------------------------------------------------------------------ the network join, on the real server
@pytest.fixture
def net(tmp_path):
    (tmp_path / "srv").mkdir()
    running = Running(tmp_path / "srv")
    owner = Owner.create(MemoryVault(), FAST, cloud=running.client())
    owner.pair_cloud(running.core.public_identity())
    running.core.pair_owner(owner.public_identity())
    owner.create_group("Finance")
    owner.add_document("Finance", "Contract A", "the penalty clause is confidential", ["contract", "confidential"])
    owner.publish("Finance")
    yield running, owner
    running.close()


def receiver_for(running: Running, owner: Owner, name: str = "dana") -> Receiver:
    rec = Receiver.create(MemoryVault(), FAST, name, cloud=running.client())
    rec.pair(PublicIdentity.from_wire(running.client().call("owner_pub", None)), running.core.public_identity())
    return rec


def test_join_with_an_invite_end_to_end(net):
    running, owner = net
    inv = owner.create_invite("127.0.0.1", running.config.port, running.pin, "dana")
    assert PublicIdentity.from_wire(running.client().call("owner_pub", None)).fingerprint() == inv.owner_fp
    dana = receiver_for(running, owner)
    uid = dana.send_join(inv.id, inv.code)
    [pending] = [i for i in owner.pending_joins() if i["uid"] == uid]
    request = owner.check_join(pending)
    assert request.invite == inv.id and request.invite_name == "dana"
    owner.approve_join(pending, ["Finance"])
    dana.fetch_mail()
    assert len(dana.search("Finance", "confidential").hits) == 1
    assert owner.invites()[0]["used"] is True


def test_invites_are_single_use_checked_and_required(net):
    running, owner = net
    inv = owner.create_invite("127.0.0.1", running.config.port, running.pin, "dana")
    first = receiver_for(running, owner, "dana")
    first.send_join(inv.id, inv.code)
    second = receiver_for(running, owner, "eve")
    for kwargs, reason in [(dict(invite_id=inv.id, code=inv.code), "invite_used"),
                           (dict(invite_id="00" * 16, code=inv.code), "bad_invite"),
                           (dict(), "invite_required")]:
        with pytest.raises(Rejected) as info:
            second.send_join(**kwargs)
        assert info.value.reason == reason
    fresh = owner.create_invite("127.0.0.1", running.config.port, running.pin, "eve")
    with pytest.raises(Rejected) as info:
        second.send_join(fresh.id, "WRONG-CODE-1234")
    assert info.value.reason == "bad_invite"
    expired = owner.create_invite("127.0.0.1", running.config.port, running.pin, "late", days=-1)
    with pytest.raises(Rejected) as info:
        second.send_join(expired.id, expired.code)
    assert info.value.reason == "invite_expired"


def test_the_server_cannot_forge_the_owners_invite_proof():
    world = World()
    owner = world.owner
    owner.create_group("g")
    inv = owner.create_invite("127.0.0.1", 1, "ab" * 32, "mallory")
    rec = world.new_receiver("mallory")
    request = rec.join_request(inv.id, inv.code)
    k_server, _ = invites.keys_from_code(inv.code)
    request["proof_o"] = invites.proof(k_server, request["req"])     # what a server holding only k_server could make
    world.cloud.handle("join_post", wire.enc(request))
    [item] = owner.pending_joins()
    with pytest.raises(VerifyError):
        owner.check_join(item)


def test_only_the_owner_lists_joins_and_only_the_receiver_reads_its_mail(net):
    running, owner = net
    inv = owner.create_invite("127.0.0.1", running.config.port, running.pin, "dana")
    dana = receiver_for(running, owner)
    dana.send_join(inv.id, inv.code)
    owner.approve_join(owner.pending_joins()[0], ["Finance"])
    stranger = Owner.create(MemoryVault(), FAST, cloud=running.client())
    with pytest.raises(Rejected) as info:
        stranger.pending_joins()
    assert info.value.reason == "bad_signature"
    other = receiver_for(running, owner, "eve")
    other.uid = dana.uid                                               # asks for dana's mail, signs with its own key
    with pytest.raises(Rejected) as info:
        other.mail_items()
    assert info.value.reason == "bad_signature"
    assert [m["kind"] for m in dana.mail_items()] == ["cap"]


# ------------------------------------------------------------------ documents in parts
def test_documents_arrive_in_parts_and_a_broken_download_resumes(monkeypatch):
    monkeypatch.setattr(receiver_module, "DOWNLOAD_PART", 1000)
    world = World()
    world.owner.create_group("g")
    [doc_id] = world.owner.build_index("g", [DocInput("big", "x" * 5000 + " needle", ["needle"])])
    world.owner.publish("g")
    bob = world.join("receiver-a", ["g"])
    [(hit, epoch)] = bob.search("g", "needle").hits

    class Flaky:
        def __init__(self, inner, fail_at):
            self.inner, self.fail_at, self.parts = inner, fail_at, []

        def call(self, endpoint, obj):
            if endpoint == "doc_get":
                self.parts.append(1)
                if len(self.parts) == self.fail_at:
                    raise CloudUnavailable("connection lost in the middle of the download")
            return self.inner.call(endpoint, obj)

    flaky = Flaky(world.api, fail_at=3)
    bob.cloud = flaky
    with pytest.raises(CloudUnavailable):
        bob.open_document("g", hit, epoch)
    kept = [n for n in bob.vault.names("download:")]
    assert len(kept) == 1 and len(bob.vault.get(kept[0])["data"]) == 2000      # two parts kept, encrypted at rest
    resumed = Flaky(world.api, fail_at=0)
    bob.cloud = resumed
    doc = bob.open_document("g", hit, epoch)
    assert doc.text.endswith("needle") and not list(bob.vault.names("download:"))
    assert len(resumed.parts) < 6                                               # it did not start again from zero


# ------------------------------------------------------------------ the app: invite a person, join with an invite
def test_session_invite_flow(net):
    running, owner_core = net
    from app.session import Session
    owner_session = Session()
    owner_session.set_use("owner")
    owner_session.connect_server("127.0.0.1", running.config.port, running.pin, running.core.public_identity().fingerprint())
    owner_session.owner = owner_core
    owner_core.cloud = owner_session.api()
    made = owner_session.create_invite("dana")
    assert made["code"] and made["file"].endswith(".pqinvite") and made["code"] not in open(made["file"]).read()
    recv_session = Session()
    recv_session.settings["kem"], recv_session.settings["sig"] = FAST.kem, FAST.sig
    joined = recv_session.join_with_invite(made["link"], made["code"], "dana", "dana passphrase")
    assert len(joined["words"].split()) == 6
    [pending] = owner_core.pending_joins()
    assert owner_core.check_join(pending).invite_name == "dana"
    owner_session.owner = None
    owner_session.close()
    recv_session.close()
