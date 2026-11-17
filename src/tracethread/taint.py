"""A model for testing recall and hold policies. Not a description of how
payment networks behave today.

Given the legs of a case, the leg or legs a victim reported, and a set of
assumptions about who hears about the fraud when and what they do, replay
the case and count how much of the reported value ends up frozen and how
much is returned. Change the assumptions and compare.

What is real and what is assumed:

- Nothing propagates by itself. On FedNow, a participant's negative list is
  its own and is not shared; on RTP and FedNow, a fraud report goes to the
  network and to the other bank in that payment. Whether the next bank down
  the line hears anything depends on someone sending it a recall (camt.056)
  or a request through FFKC or 314(b). The ``chain`` mode models that with a
  delay per hop.
- The ``broadcast`` mode, where every bank that received tainted value hears
  at once, is a hypothetical for comparison. No network does this today.
- A stablecoin issuer can freeze an address under its own policy or a lawful
  order (GENIUS Act, Pub. L. 119-27, sec. 4(a)(5)(A)(iv)). Model it as an
  institution with a hold delay that stands for the time to get that order or
  decision.
- A hold freezes the tainted balance at that moment and any tainted value
  that reaches the account later. Clean value stays spendable.
- A hold is not a return. The RTP Request for Return guidelines say the
  receiving bank has no obligation to return funds; ``returns`` is per
  institution for that reason.

Taint accounting follows one of five rules. ``fifo``, ``lifo`` and
``haircut`` are the usual tracing conventions; ``tainted_first`` and
``clean_first`` bound them from above and below. All amounts are integers in
one unit; the simulator refuses mixed currencies unless told they trade at
par.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Literal

from .model import Leg

Method = Literal["fifo", "lifo", "haircut", "tainted_first", "clean_first"]
METHODS: tuple[Method, ...] = ("fifo", "lifo", "haircut", "tainted_first", "clean_first")


class SimError(ValueError):
    pass


@dataclass(frozen=True)
class InstPolicy:
    responds: bool = True
    hold_delay: int = 0
    returns: bool = True


@dataclass(frozen=True)
class Scenario:
    name: str
    report_ts: int
    mode: Literal["chain", "broadcast", "none"] = "chain"
    hop_delay: int = 4 * 3600
    broadcast_delay: int = 300
    max_hops: int | None = None
    method: Method = "fifo"
    default: InstPolicy = InstPolicy()
    institutions: dict[str, InstPolicy] = field(default_factory=dict)

    def policy(self, inst: str) -> InstPolicy:
        return self.institutions.get(inst, self.default)


@dataclass
class Result:
    scenario: str
    seeded: int
    frozen: dict[str, int]
    returned: int
    blocked: int
    notices: dict[str, int]
    leg_taint: dict[str, int]
    unfunded: int

    @property
    def frozen_total(self) -> int:
        return sum(self.frozen.values())

    @property
    def unrecovered(self) -> int:
        return self.seeded - self.returned


class _Account:
    """Balance split into clean and tainted value under one accounting rule."""

    def __init__(self, method: Method) -> None:
        self.method = method
        self.lots: deque[tuple[int, bool]] = deque()
        self.clean = 0
        self.tainted = 0
        self.frozen = 0
        self.on_hold = False

    def credit(self, amount: int, tainted_part: int) -> None:
        clean_part = amount - tainted_part
        if self.on_hold:
            # A restricted account keeps whatever tainted value still arrives.
            self.frozen += tainted_part
            tainted_part = 0
        if self.method in ("fifo", "lifo"):
            if clean_part:
                self.lots.append((clean_part, False))
            if tainted_part:
                self.lots.append((tainted_part, True))
        self.clean += clean_part
        self.tainted += tainted_part

    @property
    def spendable(self) -> int:
        return self.clean + self.tainted

    def debit(self, amount: int) -> int:
        """Take ``amount`` (at most the spendable balance); return its tainted part."""
        amount = min(amount, self.spendable)
        if amount <= 0:
            return 0
        if self.method == "haircut":
            t = amount * self.tainted // self.spendable
        elif self.method == "tainted_first":
            t = min(amount, self.tainted)
        elif self.method == "clean_first":
            t = max(0, amount - self.clean)
        else:
            t, need = 0, amount
            while need:
                lot, is_t = self.lots.popleft() if self.method == "fifo" else self.lots.pop()
                take = min(lot, need)
                need -= take
                t += take if is_t else 0
                if take < lot:
                    rest = (lot - take, is_t)
                    if self.method == "fifo":
                        self.lots.appendleft(rest)
                    else:
                        self.lots.append(rest)
        self.tainted -= t
        self.clean -= amount - t
        return t

    def freeze_tainted(self) -> int:
        n = self.tainted
        if self.method in ("fifo", "lifo"):
            self.lots = deque(lot for lot in self.lots if not lot[1])
        self.tainted = 0
        self.frozen += n
        self.on_hold = True
        return n


def _check_units(legs: list[Leg], par: frozenset[str]) -> None:
    units = {leg.currency for leg in legs if leg.moves_value()}
    if len(units) > 1 and not units <= par:
        raise SimError(f"legs use {sorted(units)}; convert to one unit first, or list them as trading at par")


def _replay(
    legs: list[Leg],
    seeds: set[str],
    method: Method,
    freezes: dict[int, list[str]] | None = None,
    injections: dict[str, int] | None = None,
) -> tuple[dict[str, _Account], dict[str, int], dict[str, int], dict[str, int], int]:
    """One pass over the legs. Returns accounts, tainted part per leg, deficit
    per leg (value that came from outside the case), amount blocked per leg,
    and the total frozen."""
    accts: dict[str, _Account] = defaultdict(lambda: _Account(method))
    leg_taint: dict[str, int] = {}
    deficit: dict[str, int] = {}
    blocked: dict[str, int] = {}
    pending = sorted((freezes or {}).items())
    i = 0
    for leg in legs:
        if not leg.moves_value():
            continue
        while i < len(pending) and pending[i][0] <= leg.ts:
            for party in pending[i][1]:
                accts[party].freeze_tainted()
            i += 1
        src = accts[leg.from_party]
        if leg.id in seeds:
            # The reported leg: the victim's money, tainted from here on.
            leg_taint[leg.id] = leg.amount
            accts[leg.to_party].credit(leg.amount, leg.amount)
            continue
        if injections is None:
            short = max(0, leg.amount - src.spendable)
            if short:
                deficit[leg.id] = short
                src.credit(short, 0)
            amount = leg.amount
        else:
            inj = injections.get(leg.id, 0)
            if inj:
                src.credit(inj, 0)
            amount = min(leg.amount, src.spendable)
            if amount < leg.amount and src.on_hold:
                # Stopped by a hold on this account. Shortfalls further down
                # only mean the money never arrived, and are not counted.
                stopped = min(leg.amount - amount, src.frozen)
                if stopped:
                    blocked[leg.id] = stopped
        t = src.debit(amount)
        leg_taint[leg.id] = t
        accts[leg.to_party].credit(amount, t)
    while i < len(pending):
        for party in pending[i][1]:
            accts[party].freeze_tainted()
        i += 1
    return accts, leg_taint, deficit, blocked, sum(a.frozen for a in accts.values())


def institutions_of(legs: list[Leg]) -> dict[str, str]:
    inst: dict[str, str] = {}
    for leg in legs:
        if leg.from_inst:
            inst.setdefault(leg.from_party, leg.from_inst)
        if leg.to_inst:
            inst.setdefault(leg.to_party, leg.to_inst)
    return inst


def notices(legs: list[Leg], seeds: set[str], sc: Scenario, leg_taint: dict[str, int]) -> dict[str, int]:
    """When each institution that received tainted value first hears of the fraud."""
    inst = institutions_of(legs)
    flows: dict[str, list[tuple[int, str]]] = defaultdict(list)
    reached: dict[str, int] = {}
    for leg in legs:
        if not leg.moves_value() or not leg_taint.get(leg.id):
            continue
        to_i = inst.get(leg.to_party, f"unknown:{leg.to_party}")
        from_i = inst.get(leg.from_party, f"unknown:{leg.from_party}")
        reached.setdefault(to_i, leg.ts)
        if leg.id in seeds:
            flows["@report"].append((leg.ts, to_i))
        elif from_i != to_i:
            flows[from_i].append((leg.ts, to_i))
    if sc.mode == "none":
        return {}
    if sc.mode == "broadcast":
        return {i: sc.report_ts + sc.broadcast_delay for i in reached}
    out: dict[str, int] = {}
    frontier = [("@report", sc.report_ts, 0)]
    while frontier:
        frontier.sort(key=lambda x: x[1])
        src, t, h = frontier.pop(0)
        if src != "@report" and not sc.policy(src).responds:
            continue
        if sc.max_hops is not None and h >= sc.max_hops:
            continue
        for _, dst in flows.get(src, []):
            when = t + sc.hop_delay
            if dst not in out or when < out[dst]:
                out[dst] = when
                frontier.append((dst, when, h + 1))
    return out


def simulate(legs: list[Leg], seeds: set[str], sc: Scenario, par: frozenset[str] = frozenset()) -> Result:
    legs = sorted(legs, key=lambda x: (x.ts, x.id))
    ids = {leg.id for leg in legs}
    if not seeds or not seeds <= ids:
        raise SimError(f"unknown seed legs: {sorted(seeds - ids) or 'none given'}")
    _check_units(legs, par)
    if sc.method not in METHODS:
        raise SimError(f"method must be one of {METHODS}")
    _, base_taint, deficit, _, _ = _replay(legs, seeds, sc.method)
    heard = notices(legs, seeds, sc, base_taint)
    inst = institutions_of(legs)
    holds: dict[int, list[str]] = defaultdict(list)
    party_inst = defaultdict(list)
    for party, i in inst.items():
        party_inst[i].append(party)
    for i, t in heard.items():
        pol = sc.policy(i)
        if not pol.responds:
            continue
        for party in party_inst.get(i, []):
            holds[t + pol.hold_delay].append(party)
    accts, leg_taint, _, blocked, _ = _replay(legs, seeds, sc.method, holds, deficit)
    frozen: dict[str, int] = defaultdict(int)
    returned = 0
    for party, a in accts.items():
        if a.frozen:
            i = inst.get(party, f"unknown:{party}")
            frozen[i] += a.frozen
            if sc.policy(i).returns:
                returned += a.frozen
    seeded = sum(leg.amount for leg in legs if leg.id in seeds)
    return Result(
        scenario=sc.name,
        seeded=seeded,
        frozen=dict(sorted(frozen.items())),
        returned=returned,
        blocked=sum(blocked.values()),
        notices=dict(sorted(heard.items(), key=lambda kv: kv[1])),
        leg_taint=leg_taint,
        unfunded=sum(deficit.values()),
    )
