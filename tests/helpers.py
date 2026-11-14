"""Workload helpers shared by the test files."""
from __future__ import annotations

import random

from pqsse.owner import DocInput
from pqsse.sandbox import World

VOCAB = ["lattice", "kyber", "dilithium", "token", "cloud", "owner", "receiver", "epoch", "segment",
         "revoke", "search", "index", "chain", "state", "fresh", "quantum", "module", "signature",
         "cipher", "nonce", "group", "policy", "verify", "padding"]


def random_doc(rng: random.Random, vocab: list[str] = VOCAB) -> DocInput:
    words = rng.sample(vocab, rng.randint(2, min(7, len(vocab))))
    return DocInput(f"note {rng.randrange(10**6)}", " ".join(words))


def filled_world(groups: list[str], docs_per_group: int, seed: int = 1, vocab: list[str] = VOCAB, **kwargs) -> tuple[World, random.Random]:
    """A world with groups created, an initial BuildIndex per group, and states published."""
    rng = random.Random(seed)
    world = World(**kwargs)
    for g in groups:
        world.owner.create_group(g)
        world.owner.build_index(g, [random_doc(rng, vocab) for _ in range(docs_per_group)])
        world.owner.publish(g)
    return world, rng


def random_update(world: World, g: str, rng: random.Random, vocab: list[str] = VOCAB) -> str:
    """Apply one random add, delete or edit to a group. Returns the operation name."""
    docs = world.owner.documents(g)
    roll = rng.random()
    if roll < 0.5 or not docs:
        doc = random_doc(rng, vocab)
        world.owner.add_document(g, doc.title, doc.text)
        return "add"
    victim = rng.choice(docs)["id"]
    if roll < 0.8:
        world.owner.delete_document(g, victim)
        return "delete"
    doc = random_doc(rng, vocab)
    world.owner.edit_document(g, victim, doc.title, doc.text)
    return "edit"
