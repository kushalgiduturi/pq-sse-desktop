"""Design note 004 A: several independent data owners on one server."""
from __future__ import annotations

import dataclasses

import pytest
from test_m16_server import FAST, PASS, Running

from pqsse.cloud.core import CloudCore
from pqsse.cloud.multi import OwnerRouter, owner_id
from pqsse.core import wire
from pqsse.core.errors import Rejected
from pqsse.core.keystore import MemoryVault
from pqsse.owner import Owner
from pqsse.receiver import Receiver
from pqsse.server import store
from pqsse.transport import InProcessCloud


def in_process_router() -> OwnerRouter:
    default = CloudCore(MemoryVault(), FAST)
    identity = default.vault.get("identity")

    def open_store(oid: str) -> CloudCore:
        vault = MemoryVault()
        vault.put("identity", identity)
        return CloudCore(vault, FAST)
    return OwnerRouter(default, open_store)


def new_owner(router: OwnerRouter, api, name: str) -> Owner:
    owner = Owner.create(MemoryVault(), FAST, name, cloud=api)
    owner.pair_cloud(router.default.public_identity())
    router.add_owner(owner.public_identity())
    return owner


def join(owner: Owner, router: OwnerRouter, api, name: str, groups) -> Receiver:
    rec = Receiver.create(MemoryVault(), FAST, name, cloud=api)
    rec.pair(owner.public_identity(), router.default.public_identity())
    uid = rec.send_join()
    owner.approve_join(next(i for i in owner.pending_joins() if i["uid"] == uid), list(groups))
    rec.fetch_mail()
    return rec


def test_two_owners_with_the_same_group_name_stay_apart():
    router = in_process_router()
    api = InProcessCloud(router)
    x, y = new_owner(router, api, "x"), new_owner(router, api, "y")
    assert router.default.owner_identity().vk == x.vk and owner_id(y.vk) in router.extra
    for owner, text in ((x, "x secret"), (y, "y secret")):
        owner.create_group("Finance")
        owner.add_document("Finance", f"{owner.name} doc", text, ["secret"])
        owner.publish("Finance")
    rx, ry = join(x, router, api, "rx", ["Finance"]), join(y, router, api, "ry", ["Finance"])
    assert {rx.open_document("Finance", d, e).text for d, e in rx.search("Finance", "secret").hits} == {"x secret"}
    assert {ry.open_document("Finance", d, e).text for d, e in ry.search("Finance", "secret").hits} == {"y secret"}
    assert x.pending_joins() == [] and len(router.extra[owner_id(y.vk)].db.execute("SELECT * FROM creds").fetchall()) == 1
    assert [o["first"] for o in router.owners()] == [True, False]


def test_one_owner_cannot_act_for_another_and_unknown_owners_are_refused():
    router = in_process_router()
    api = InProcessCloud(router)
    x, y = new_owner(router, api, "x"), new_owner(router, api, "y")
    y.create_group("Finance")

    class PretendsToBeY:
        def call(self, endpoint, obj):
            return api.call(endpoint, {**obj, "owner": owner_id(y.vk)} if isinstance(obj, dict) else obj)

    x.cloud = PretendsToBeY()                         # x's signed messages sent to y's store
    with pytest.raises(Rejected) as info:
        x.create_group("Finance")
    assert info.value.reason == "bad_signature"
    with pytest.raises(Rejected) as info:
        api.call("join_list", {"owner": "00" * 8, "ts": 0, "sig": b""})
    assert info.value.reason == "unknown_owner"


def test_sequence_numbers_are_per_owner_and_one_owner_requests_need_no_tag():
    router = in_process_router()
    api = InProcessCloud(router)
    x, y = new_owner(router, api, "x"), new_owner(router, api, "y")
    for _ in range(3):
        x.create_group(f"g{_}")
    y.create_group("only")
    assert x._meta["ctl_seq"] == 3 and y._meta["ctl_seq"] == 1
    assert wire.dec(router.handle("info", wire.enc(None)))["paired"] is True        # untagged: the first owner
    by_fp = wire.dec(router.handle("owner_pub", wire.enc({"fp": y.public_identity().fingerprint()})))
    assert by_fp["vk"] == y.vk
    with pytest.raises(Rejected):
        router.handle("owner_pub", wire.enc({"fp": "not a fingerprint"}))


def test_the_server_keeps_further_owners_across_a_restart_check_backup_and_restore(tmp_path):
    first = Running(tmp_path)
    router = store.open_router(first.config, PASS)
    first.public.core = router                                    # serve the router, as `pqsse.server run` does
    try:
        api = first.client()
        x = Owner.create(MemoryVault(), FAST, "x", cloud=api)
        x.pair_cloud(router.default.public_identity())
        router.add_owner(x.public_identity())
        y = Owner.create(MemoryVault(), FAST, "y", cloud=api)
        y.pair_cloud(router.default.public_identity())
        router.add_owner(y.public_identity())
        y.create_group("Finance")
        y.add_document("Finance", "y doc", "y secret", ["secret"])
        y.publish("Finance")
        owner_dir = first.config.data_dir / "owners" / owner_id(y.vk)
        assert (owner_dir / "cloud.sqlite").is_file() and store.check(first.config) == []
        dest = store.backup(first.config, tmp_path / "backup")
        assert (dest / "owners" / owner_id(y.vk) / "cloud.sqlite").is_file()
    finally:
        router.close()
        first.close()
    target = dataclasses.replace(first.config, data_dir=tmp_path / "restored")
    store.restore(dest, target)
    reopened = store.open_router(target, PASS)
    try:
        assert owner_id(y.vk) in reopened.extra
        assert reopened.core_for(owner_id(y.vk)).db.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 1
        assert reopened.core_for(owner_id(y.vk)).public_identity().vk == reopened.default.public_identity().vk
    finally:
        reopened.close()


def test_a_store_paired_by_another_process_is_found_without_a_restart(tmp_path):
    running = Running(tmp_path)
    router = store.open_router(running.config, PASS)
    try:
        y = Owner.create(MemoryVault(), FAST, "y")
        other = store.open_router(running.config, PASS)          # the CLI, while the server runs
        other.add_owner(Owner.create(MemoryVault(), FAST, "x").public_identity())   # first owner
        oid = other.add_owner(y.public_identity())
        other.extra[oid].vault.close()
        assert router.core_for(oid).owner_identity().vk == y.vk
    finally:
        router.close()
        running.close()
