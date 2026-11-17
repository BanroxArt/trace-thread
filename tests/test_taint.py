from __future__ import annotations

import pytest
from conftest import leg
from hypothesis import given, settings
from hypothesis import strategies as st

from tracethread import InstPolicy, Scenario, SimError, simulate
from tracethread.taint import METHODS, _replay

H = 3600


def chain_case() -> list:
    return [
        leg("L1", "victim", "m1", 100_000, 0, from_inst="A", to_inst="B"),
        leg("L2", "m1", "m2", 95_000, 600, from_inst="B", to_inst="C"),
        leg("L3", "m2", "exit", 90_000, H, from_inst="C", to_inst="X"),
    ]


def test_manual_chain_vs_broadcast() -> None:
    legs = chain_case()
    offshore = {"X": InstPolicy(responds=False)}
    slow = Scenario("chain", report_ts=legs[0].ts + 1800, hop_delay=H, institutions=offshore)
    r = simulate(legs, {"L1"}, slow)
    # B hears at 1800+3600, after m1 sent 95,000 on; C hears an hour later, after m2 sent 90,000
    # to X, which does not act on recalls.
    assert r.frozen == {"B": 5_000, "C": 5_000}
    assert r.returned == 10_000 and r.unrecovered == 90_000 and r.blocked == 0
    fast = Scenario(
        "broadcast", report_ts=legs[0].ts + 1800, mode="broadcast", broadcast_delay=300, institutions=offshore
    )
    r2 = simulate(legs, {"L1"}, fast)
    assert r2.frozen == {"B": 5_000, "C": 95_000}
    assert r2.blocked == 90_000 and r2.returned == 100_000
    assert r2.leg_taint["L3"] == 0


def test_returns_are_per_institution_and_none_mode() -> None:
    legs = chain_case()
    sc = Scenario(
        "c-keeps",
        report_ts=legs[0].ts + 1800,
        mode="broadcast",
        broadcast_delay=300,
        institutions={"C": InstPolicy(returns=False)},
    )
    r = simulate(legs, {"L1"}, sc)
    assert r.frozen_total == 100_000 and r.returned == 5_000
    off = simulate(legs, {"L1"}, Scenario("none", report_ts=legs[0].ts, mode="none"))
    assert off.frozen_total == 0 and off.notices == {}


def test_hops_stop_and_non_responders_break_the_chain() -> None:
    legs = chain_case()
    one = simulate(legs, {"L1"}, Scenario("x", legs[0].ts + 60, hop_delay=60, max_hops=1))
    assert set(one.notices) == {"B"}
    mute = simulate(
        legs,
        {"L1"},
        Scenario("x", legs[0].ts + 60, hop_delay=60, institutions={"B": InstPolicy(responds=False)}),
    )
    assert set(mute.notices) == {"B"} and mute.frozen_total == 0


def test_hold_delay_stands_for_a_lawful_order() -> None:
    legs = chain_case()
    sc = Scenario(
        "order",
        legs[0].ts,
        mode="broadcast",
        broadcast_delay=0,
        institutions={"B": InstPolicy(hold_delay=3 * H)},
    )
    r = simulate(legs, {"L1"}, sc)
    assert r.frozen["B"] == 5_000 and r.frozen["C"] == 95_000


def test_methods_on_a_mixed_account() -> None:
    legs = [
        leg("own", "salary", "m", 100, 0),
        leg("bad", "victim", "m", 100, 10),
        leg("out", "m", "n", 100, 20),
    ]
    want = {"fifo": 0, "lifo": 100, "haircut": 50, "tainted_first": 100, "clean_first": 0}
    for method in METHODS:
        _, taint, _, _, _ = _replay(legs, {"bad"}, method)
        assert taint["out"] == want[method], method


def test_unfunded_outflows_are_outside_money() -> None:
    legs = [leg("bad", "v", "m", 100, 0), leg("out", "m", "n", 250, 10)]
    r = simulate(legs, {"bad"}, Scenario("x", legs[0].ts + 20, mode="broadcast", broadcast_delay=0))
    assert r.unfunded == 150 and r.leg_taint["out"] == 100


def test_refuses_mixed_units_and_bad_seeds() -> None:
    legs = [leg("a", "v", "m", 100), leg("b", "m", "n", 90, 60, currency="USDC")]
    with pytest.raises(SimError):
        simulate(legs, {"a"}, Scenario("x", 0))
    assert simulate(legs, {"a"}, Scenario("x", 0), par=frozenset({"USD", "USDC"})).seeded == 100
    with pytest.raises(SimError):
        simulate(legs, {"zz"}, Scenario("x", 0), par=frozenset({"USD", "USDC"}))


flows = st.lists(
    st.tuples(st.integers(0, 4), st.integers(0, 4), st.integers(1, 1000), st.integers(1, 5000)),
    min_size=1,
    max_size=25,
)


@settings(max_examples=150, deadline=None)
@given(flows, st.sampled_from(METHODS), st.sampled_from(["chain", "broadcast"]), st.integers(0, 6 * H))
def test_conservation(raw: list[tuple[int, int, int, int]], method: str, mode: str, delay: int) -> None:
    legs = [leg("seed", "victim", "p0", 1000, 0, from_inst="V", to_inst="I0")]
    for n, (f, t, amt, dt) in enumerate(raw):
        if f == t:
            continue
        legs.append(leg(f"x{n}", f"p{f}", f"p{t}", amt, dt, from_inst=f"I{f}", to_inst=f"I{t}"))
    accts, taint, _, _, _ = _replay(sorted(legs, key=lambda x: (x.ts, x.id)), {"seed"}, method)  # type: ignore[arg-type]
    assert sum(a.tainted for a in accts.values()) == 1000
    assert all(0 <= taint[k] <= x.amount for x in legs for k in [x.id])
    sc = Scenario(
        "p", report_ts=legs[0].ts + delay, mode=mode, hop_delay=H, broadcast_delay=300, method=method
    )  # type: ignore[arg-type]
    r = simulate(legs, {"seed"}, sc)
    assert 0 <= r.returned <= r.frozen_total <= r.seeded == 1000
