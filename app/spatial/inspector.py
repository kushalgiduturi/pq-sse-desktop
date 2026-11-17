"""Step Inspector content: the four layers for one recorded event or one attack.

Everything here is plain data (dicts of strings and numbers) built from narrator events,
so it can be tested without a window and can never contain key material: narrator facts
are numbers, short strings and lists of strings only.
"""
from __future__ import annotations

from pqsse import attacklab, narrator

from ..glossary import GLOSSARY
from .copy import ATTACK_STEPS, INSPECT, PRIMITIVES, TERMS, T

ANIMATIONS = ("encrypt", "kem", "sign", "search", "verify", "move", "update", "revoke")


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "?"


def _facts(event: narrator.Event) -> _Safe:
    facts = _Safe({k: ((", ".join(v) or "none") if isinstance(v, (list, tuple)) else v) for k, v in event.data.items()})
    facts["who"] = event.who or "Someone"
    return facts


def build(event: narrator.Event, took_ms: float | None = None) -> dict:
    """The inspector record for one event: title, four layers, sub-steps, animation name."""
    text = narrator.render(event)
    spec = INSPECT[event.kind]
    facts = _facts(event)
    steps = [step.format_map(facts) for step in spec["steps"]]
    hood = [text.technical] + ([text.hood] if text.hood else []) + [PRIMITIVES[p] for p in spec["prims"]]
    if not spec["prims"]:
        hood.append("No cryptographic operation happens in this step.")
    engine = str(event.data.get("engine", ""))
    if engine:
        hood.append("Batch work done on: " + engine + ". ML-KEM and ML-DSA always run on the CPU.")
    safe = spec["safe"].format_map(facts)
    packet = text.packet
    record = {
        "kind": event.kind,
        "scope": event.scope,
        "title": text.technical.split(",")[0],
        "technical": text.technical,
        "algorithm": narrator.algorithm_of(event.kind),
        "who": event.who,
        "tag": text.tag,
        "tagLabel": text.tag_label,
        "line": text.line,
        "more": text.more,
        "anim": spec["anim"],
        "reverse": bool(spec.get("reverse")),
        "steps": steps,
        "hood": hood,
        "safe": safe,
        "metaphor": spec["metaphor"],
        "simplification": spec.get("simplification", ""),
        "facts": {k: str(v) for k, v in facts.items()},
        "terms": [{"key": key, "name": GLOSSARY[key].name} for key in dict.fromkeys(TERMS[p] for p in spec["prims"]) if key in GLOSSARY],
        "ts": event.ts,
        "tookMs": -1.0 if took_ms is None else round(took_ms, 1),
        "replayNote": T["replayNoteUnknown"] if took_ms is None else T["replayNote"].format(ms=f"{took_ms:.0f}"),
        "packet": None if packet is None else {"src": packet.src, "dst": packet.dst, "icon": packet.icon, "label": packet.label,
                                               "contents": packet.contents, "readers": packet.readers},
    }
    return record


def layers(record: dict) -> dict[str, str]:
    """The four layers as plain text (used by tests and by the screen reader text)."""
    return {
        "plain": record["line"] + " " + record["more"],
        "moved": " ".join(f"{i + 1}. {step}" for i, step in enumerate(record["steps"])),
        "hood": " ".join(record["hood"]),
        "safe": record["safe"] + " " + T["metaphor"] + record["metaphor"],
    }


def build_attack(key: str, outcome: attacklab.Outcome | None = None) -> dict:
    """The inspector record for one Security Lab scenario (before or after it ran)."""
    title = next(t for k, t, _, _ in attacklab.SCENARIOS if k == key)
    description = next(d for k, _, d, _ in attacklab.SCENARIOS if k == key)
    teach = attacklab.TEACH[key]
    caught = outcome.caught_by if outcome else "run the attack to see it"
    verdict = outcome.verdict if outcome else "not run yet"
    facts = _Safe(tries=teach["tries"], caught_by=caught, verdict=verdict)
    return {
        "kind": "attack:" + key,
        "title": title,
        "technical": "Security Lab scenario: " + title,
        "algorithm": 0,
        "who": "Attacker",
        "tag": "security",
        "tagLabel": "Security",
        "line": description,
        "more": teach["tries"],
        "anim": "verify",
        "reverse": False,
        "steps": [step.format_map(facts) for step in ATTACK_STEPS],
        "hood": ["Runs on a separate practice copy with the same code as the real system.",
                 "Check or refusal: " + (outcome.check if outcome and outcome.check else "shown after the run"),
                 PRIMITIVES["sig"], PRIMITIVES["hash"]],
        "safe": "Without this protection: " + teach["without"],
        "metaphor": INSPECT["attack"]["metaphor"],
        "simplification": teach.get("unprotected", ""),
        "facts": {k: str(v) for k, v in facts.items()},
        "terms": [{"key": key, "name": GLOSSARY[key].name} for key in ("signature", "hash-chain", "freshness") if key in GLOSSARY],
        "ts": 0.0,
        "tookMs": -1.0,
        "replayNote": T["replayNoteUnknown"],
        "packet": None,
        "checks": [[name, ok] for name, ok in (outcome.checks if outcome else [])],
        "passed": bool(outcome.passed) if outcome else False,
    }
