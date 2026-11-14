"""A throwaway three-party world in memory.

Used by the tests, the benchmarks and the Attack Lab. The three parties are separate
objects that talk only through wire messages (InProcessCloud calls CloudCore.handle
with encoded bytes), exactly like the HTTP deployment.
"""
from __future__ import annotations

import time
from typing import Sequence

from .cloud.core import CloudCore
from .core.keystore import MemoryVault
from .gpu.batchprf import BatchPRF
from .owner.owner import Owner
from .pqbackend import FAST_PARAMS, Params
from .receiver.receiver import Receiver
from .transport import CloudAPI, InProcessCloud


class Clock:
    """Adjustable clock so tests can move time forward (freshness, expiry)."""

    def __init__(self) -> None:
        self.offset = 0.0

    def __call__(self) -> float:
        return time.time() + self.offset

    def advance(self, seconds: float) -> None:
        self.offset += seconds


class World:
    """Owner, cloud and any number of receivers, already paired."""

    def __init__(self, params: Params = FAST_PARAMS, prf: BatchPRF | None = None,
                 state_ttl: float = 3600.0, keep_log: bool = False) -> None:
        self.params = params
        self.clock = Clock()
        self.cloud = CloudCore(MemoryVault(), params, clock=self.clock, keep_log=keep_log)
        self.api: CloudAPI = InProcessCloud(self.cloud)
        self.owner = Owner.create(MemoryVault(), params, cloud=self.api, prf=prf, clock=self.clock, state_ttl=state_ttl)
        self.owner.pair_cloud(self.cloud.public_identity())
        self.cloud.pair_owner(self.owner.public_identity())
        self.receivers: dict[str, Receiver] = {}
        self.prf = prf

    def new_receiver(self, name: str, api: CloudAPI | None = None) -> Receiver:
        """Create and pair a receiver without joining."""
        rec = Receiver.create(MemoryVault(), self.params, name, cloud=api or self.api, prf=self.prf, clock=self.clock)
        rec.pair(self.owner.public_identity(), self.cloud.public_identity())
        self.receivers[name] = rec
        return rec

    def join(self, name: str, groups: Sequence[str], api: CloudAPI | None = None) -> Receiver:
        """Run the whole Join algorithm for a new receiver."""
        rec = self.new_receiver(name, api)
        uid = rec.send_join()
        item = next(i for i in self.owner.pending_joins() if i["uid"] == uid)
        self.owner.approve_join(item, groups)
        rec.fetch_mail()
        return rec
