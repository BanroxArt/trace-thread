"""Link legs into threads.

Two kinds of link, kept apart in every output:

- identifier links, where both legs carry the same reference (a UETR, an
  IMAD, an ACH trace number on the same few days, a return that names the
  original) or the issuer's own records tie a fiat leg to a mint or burn;
- inferred links, where value lands in an account and a similar amount leaves
  it soon after. These are leads for an investigator, not evidence, and their
  confidence never reaches that of an identifier link.

The point of the split is to show where the identifier trail breaks. A
UETR follows a payment through SWIFT and Fedwire. It does not survive the
beneficiary paying someone else, and no standard carries it through a
stablecoin mint or burn.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from .model import Case, Leg

DAY = 86_400

# (reference kind, also keyed by, confidence, why)
_SHARED: tuple[tuple[str, str | None, float, str], ...] = (
    ("uetr", None, 1.0, "same UETR"),
    ("imad", None, 1.0, "same Fedwire IMAD"),
    ("omad", None, 1.0, "same Fedwire OMAD"),
    ("tx_hash", None, 1.0, "same on-chain transaction"),
    ("tx_id", "from_inst", 0.9, "same transaction ID from the same first agent"),
    ("e2e_id", "from_inst", 0.85, "same end-to-end ID from the same debtor agent"),
    ("instr_id", "from_inst", 0.85, "same instruction ID from the same instructing agent"),
    ("msg_id", "from_inst", 0.8, "same message ID from the same sender"),
    ("issuer_ref", None, 0.95, "issuer's records tie the fiat leg to the mint or burn"),
)
_ORIG = (
    ("orig_uetr", "uetr"),
    ("orig_tx_id", "tx_id"),
    ("orig_e2e_id", "e2e_id"),
    ("orig_msg_id", "msg_id"),
    ("orig_ach_trace", "ach_trace"),
    ("orig_imad", "imad"),
)
INFERRED_CAP = 0.7


@dataclass(frozen=True)
class Link:
    a: str
    b: str
    basis: str
    confidence: float
    inferred: bool
    detail: str = ""


@dataclass(frozen=True)
class Options:
    pass_through_window: int = 3 * DAY
    max_haircut_pct: int = 15
    ach_trace_days: int = 5
    min_confidence: float = 0.5


@dataclass
class Thread:
    legs: list[Leg]
    links: list[Link]
    breaks: list[Link] = field(default_factory=list)

    @property
    def rails(self) -> list[str]:
        out: list[str] = []
        for leg in self.legs:
            if leg.rail not in out:
                out.append(leg.rail)
        return out


def _chain(ids: list[Leg], basis: str, conf: float, detail: str) -> Iterable[Link]:
    ordered = sorted(ids, key=lambda x: (x.ts, x.id))
    for x, y in itertools.pairwise(ordered):
        yield Link(x.id, y.id, basis, conf, False, detail)


def identifier_links(legs: list[Leg], opts: Options) -> list[Link]:
    out: list[Link] = []
    for kind, scope, conf, why in _SHARED:
        groups: dict[tuple[str, str], list[Leg]] = defaultdict(list)
        for leg in legs:
            v = leg.ref(kind)
            if v:
                key = (v, getattr(leg, scope) if scope else "")
                groups[key].append(leg)
        for (v, _), g in groups.items():
            if len(g) > 1:
                out.extend(_chain(g, kind, conf, f"{why}: {v}"))
    # ACH trace numbers wrap, so they only identify an entry together with a date.
    traces: dict[str, list[Leg]] = defaultdict(list)
    for leg in legs:
        v = leg.ref("ach_trace")
        if v:
            traces[v].append(leg)
    for v, g in traces.items():
        g = sorted(g, key=lambda x: (x.ts, x.id))
        for x, y in itertools.pairwise(g):
            if y.ts - x.ts <= opts.ach_trace_days * DAY:
                out.append(Link(x.id, y.id, "ach_trace", 0.95, False, f"same ACH trace number: {v}"))
    # Returns and recalls name the original.
    index: dict[tuple[str, str], list[Leg]] = defaultdict(list)
    for leg in legs:
        for _, k in _ORIG:
            v = leg.ref(k)
            if v:
                index[(k, v)].append(leg)
    for leg in legs:
        for ok, k in _ORIG:
            v = leg.ref(ok)
            if not v:
                continue
            for orig in index.get((k, v), []):
                if orig.id != leg.id and orig.ts <= leg.ts:
                    basis = "recall_of" if leg.kind == "recall_request" else "return_of"
                    out.append(Link(orig.id, leg.id, basis, 1.0, False, f"{ok} = {v}"))
    return _dedupe(out)


def inferred_links(case: Case, opts: Options) -> list[Link]:
    """Value in, similar value out of the same holder within the window."""
    same: dict[str, set[str]] = defaultdict(set)
    for p1, p2, _ in case.aliases:
        same[p1].add(p2)
        same[p2].add(p1)
    outs: dict[str, list[Leg]] = defaultdict(list)
    for leg in case.legs:
        if leg.moves_value() and leg.kind != "return":
            outs[leg.from_party].append(leg)
    out: list[Link] = []
    for a in case.legs:
        if not a.moves_value() or a.amount == 0:
            continue
        holders = {a.to_party} | same[a.to_party]
        for h in holders:
            for b in outs.get(h, []):
                dt = b.ts - a.ts
                if b.id == a.id or dt <= 0 or dt > opts.pass_through_window:
                    continue
                lo = a.amount * (100 - opts.max_haircut_pct)
                if not lo <= b.amount * 100 <= a.amount * 100:
                    continue
                amount_close = 1 - (a.amount - b.amount) / (a.amount * opts.max_haircut_pct / 100 or 1)
                time_close = 1 - dt / opts.pass_through_window
                conf = round(min(INFERRED_CAP, 0.3 + 0.2 * amount_close + 0.2 * time_close), 2)
                via = f" via alias {a.to_party} = {h}" if h != a.to_party else ""
                detail = f"{b.amount} of {a.amount} left {h} after {dt}s{via}"
                out.append(Link(a.id, b.id, "pass_through", conf, True, detail))
        if not any(x.a == a.id for x in out):
            out.extend(_split(a, holders, outs, opts))
    return _dedupe(out)


def _split(a: Leg, holders: set[str], outs: dict[str, list[Leg]], opts: Options) -> list[Link]:
    """Several outflows soon after one credit that together move most of it."""
    cands = sorted(
        (b for h in holders for b in outs.get(h, []) if 0 < b.ts - a.ts <= opts.pass_through_window),
        key=lambda x: (x.ts, x.id),
    )
    taken: list[Leg] = []
    total = 0
    for b in cands:
        if (total + b.amount) * 100 > a.amount * 100:
            break
        taken.append(b)
        total += b.amount
        if total * 100 >= a.amount * (100 - opts.max_haircut_pct):
            break
    if len(taken) < 2 or total * 100 < a.amount * (100 - opts.max_haircut_pct):
        return []
    span = taken[-1].ts - a.ts
    conf = round(min(0.6, 0.35 + 0.25 * (1 - span / opts.pass_through_window)), 2)
    names = ", ".join(b.id for b in taken)
    return [
        Link(a.id, b.id, "split", conf, True, f"{len(taken)} outflows ({names}) move {total} of {a.amount}")
        for b in taken
    ]


def _dedupe(links: list[Link]) -> list[Link]:
    best: dict[tuple[str, str], Link] = {}
    for link in links:
        k = (link.a, link.b)
        if k not in best or link.confidence > best[k].confidence:
            best[k] = link
    return sorted(best.values(), key=lambda x: (x.a, x.b))


def threads(case: Case, opts: Options | None = None) -> list[Thread]:
    opts = opts or Options()
    ident = identifier_links(case.legs, opts)
    inferred = [x for x in inferred_links(case, opts) if (x.a, x.b) not in {(y.a, y.b) for y in ident}]
    usable = [x for x in ident + inferred if x.confidence >= opts.min_confidence]
    parent = {leg.id: leg.id for leg in case.legs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for link in usable:
        ra, rb = find(link.a), find(link.b)
        if ra != rb:
            parent[rb] = ra
    groups: dict[str, list[Leg]] = defaultdict(list)
    for leg in case.legs:
        groups[find(leg.id)].append(leg)
    out = []
    for members in groups.values():
        ids = {m.id for m in members}
        links = [x for x in usable if x.a in ids]
        breaks = [x for x in links if x.inferred]
        out.append(Thread(sorted(members, key=lambda x: (x.ts, x.id)), links, breaks))
    out.sort(key=lambda t: (-len(t.legs), t.legs[0].ts))
    return out
