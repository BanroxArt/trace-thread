"""Payment legs: one movement of value on one rail, with whatever identifiers
the institution that recorded it could see."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ids import check, norm

RAILS = frozenset(
    {"swift", "fedwire", "chips", "ach", "fednow", "rtp", "p2p", "book", "card", "chain", "cash", "other"}
)
KINDS = frozenset({"payment", "return", "recall_request", "mint", "burn", "transfer"})
REF_KINDS = (
    "uetr",
    "e2e_id",
    "instr_id",
    "tx_id",
    "msg_id",
    "ach_trace",
    "imad",
    "omad",
    "tx_hash",
    "issuer_ref",
    "orig_uetr",
    "orig_e2e_id",
    "orig_tx_id",
    "orig_msg_id",
    "orig_ach_trace",
    "orig_imad",
)
_FIELDS = {
    "id",
    "rail",
    "kind",
    "ts",
    "amount",
    "currency",
    "from_party",
    "to_party",
    "from_inst",
    "to_inst",
    "refs",
    "note",
}


class LegError(ValueError):
    pass


def parse_ts(v: Any) -> int:
    """Epoch seconds, or an ISO 8601 string that carries its own offset."""
    if isinstance(v, bool):
        raise LegError(f"bad timestamp {v!r}")
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        try:
            t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise LegError(f"bad timestamp {v!r}") from None
        if t.tzinfo is None:
            raise LegError(f"timestamp {v!r} has no UTC offset")
        return int(t.timestamp())
    raise LegError(f"bad timestamp {v!r}")


@dataclass(frozen=True)
class Leg:
    id: str
    rail: str
    kind: str
    ts: int
    amount: int
    currency: str
    from_party: str
    to_party: str
    from_inst: str = ""
    to_inst: str = ""
    refs: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def ref(self, kind: str) -> str | None:
        v = self.refs.get(kind)
        return norm(kind, v) if v else None

    def moves_value(self) -> bool:
        return self.kind != "recall_request"


def leg_from(d: dict[str, Any]) -> Leg:
    unknown = set(d) - _FIELDS
    if unknown:
        raise LegError(f"leg {d.get('id')!r}: unknown fields {sorted(unknown)}")
    for k in ("id", "rail", "kind", "ts", "amount", "currency", "from_party", "to_party"):
        if k not in d:
            raise LegError(f"leg {d.get('id')!r}: missing {k}")
    if d["rail"] not in RAILS:
        raise LegError(f"leg {d['id']!r}: rail must be one of {sorted(RAILS)}")
    if d["kind"] not in KINDS:
        raise LegError(f"leg {d['id']!r}: kind must be one of {sorted(KINDS)}")
    amt = d["amount"]
    if isinstance(amt, bool) or not isinstance(amt, int) or amt < 0:
        raise LegError(f"leg {d['id']!r}: amount must be a non-negative integer in minor units")
    refs = d.get("refs", {})
    if not isinstance(refs, dict):
        raise LegError(f"leg {d['id']!r}: refs must be an object")
    bad = set(refs) - set(REF_KINDS)
    if bad:
        raise LegError(f"leg {d['id']!r}: unknown reference kinds {sorted(bad)}")
    return Leg(
        id=str(d["id"]),
        rail=d["rail"],
        kind=d["kind"],
        ts=parse_ts(d["ts"]),
        amount=amt,
        currency=str(d["currency"]).upper(),
        from_party=str(d["from_party"]),
        to_party=str(d["to_party"]),
        from_inst=str(d.get("from_inst", "")),
        to_inst=str(d.get("to_inst", "")),
        refs={k: str(v) for k, v in refs.items() if v not in (None, "")},
        note=str(d.get("note", "")),
    )


@dataclass(frozen=True)
class Case:
    legs: list[Leg]
    aliases: list[tuple[str, str, str]]  # (party, party, basis)

    def by_id(self) -> dict[str, Leg]:
        return {leg.id: leg for leg in self.legs}

    def format_problems(self) -> list[tuple[str, str, str]]:
        out = []
        for leg in self.legs:
            for k, v in leg.refs.items():
                p = check(k, v)
                if p:
                    out.append((leg.id, k, p))
        return out


def load_case(path: str | Path) -> Case:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return case_from(raw)


def case_from(raw: Any) -> Case:
    if isinstance(raw, list):
        raw = {"legs": raw}
    if not isinstance(raw, dict) or not isinstance(raw.get("legs"), list):
        raise LegError("expected a list of legs or an object with a 'legs' list")
    legs = [leg_from(d) for d in raw["legs"]]
    seen: set[str] = set()
    for leg in legs:
        if leg.id in seen:
            raise LegError(f"duplicate leg id {leg.id!r}")
        seen.add(leg.id)
    aliases = []
    for a in raw.get("aliases", []):
        if not isinstance(a, dict) or not {"a", "b", "basis"} <= set(a):
            raise LegError("each alias needs a, b and basis (who says these are the same holder, and how)")
        aliases.append((str(a["a"]), str(a["b"]), str(a["basis"])))
    return Case(sorted(legs, key=lambda x: (x.ts, x.id)), aliases)
