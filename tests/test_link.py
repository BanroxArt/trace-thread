from __future__ import annotations

from conftest import leg
from hypothesis import given
from hypothesis import strategies as st

from tracethread import Case, Options, identifier_links, inferred_links, threads
from tracethread.link import INFERRED_CAP

U = "eb6305c9-1f7f-49de-aed0-16487c27b42d"
DAY = 86_400


def test_uetr_links_across_rails_and_case() -> None:
    a = leg("a", "v", "c", 100, rail="swift", refs={"uetr": U})
    b = leg("b", "c", "m", 100, 60, rail="fedwire", refs={"uetr": U.upper()})
    links = identifier_links([a, b], Options())
    assert [(x.a, x.b, x.basis, x.inferred) for x in links] == [("a", "b", "uetr", False)]


def test_e2e_is_scoped_to_the_debtor_agent() -> None:
    a = leg("a", "v", "m", 100, refs={"e2e_id": "INV-1"}, from_inst="Bank A")
    b = leg("b", "w", "n", 100, 60, refs={"e2e_id": "INV-1"}, from_inst="Bank Z")
    c = leg("c", "v", "m", 100, 90, refs={"e2e_id": "INV-1"}, from_inst="Bank A")
    pairs = {(x.a, x.b) for x in identifier_links([a, b, c], Options())}
    assert pairs == {("a", "c")}


def test_ach_trace_needs_a_date() -> None:
    a = leg("a", "v", "m", 100, rail="ach", refs={"ach_trace": "061112840000001"})
    b = leg("b", "v", "m", 100, 2 * DAY, rail="ach", refs={"ach_trace": "061112840000001"})
    c = leg("c", "q", "r", 100, 40 * DAY, rail="ach", refs={"ach_trace": "061112840000001"})
    pairs = {(x.a, x.b) for x in identifier_links([a, b, c], Options())}
    assert pairs == {("a", "b")}


def test_returns_and_recalls_name_the_original() -> None:
    a = leg("a", "v", "m", 100, rail="fednow", refs={"tx_id": "TX1"})
    r = leg("r", "m", "v", 100, DAY, rail="fednow", kind="return", refs={"orig_tx_id": "TX1"})
    q = leg("q", "v", "m", 100, 3600, rail="fednow", kind="recall_request", refs={"orig_tx_id": "TX1"})
    early = leg("e", "v", "m", 100, -60, rail="fednow", kind="return", refs={"orig_tx_id": "TX1"})
    got = {(x.a, x.b, x.basis) for x in identifier_links([a, r, q, early], Options())}
    assert ("a", "r", "return_of") in got and ("a", "q", "recall_of") in got
    assert not any(x[1] == "e" and x[0] == "a" for x in got)


def test_pass_through_bounds() -> None:
    a = leg("a", "v", "m", 10_000)
    keep85 = leg("b", "m", "n", 8_500, 600)
    assert [x.basis for x in inferred_links(Case([a, keep85], []), Options())] == ["pass_through"]
    keep84 = leg("b", "m", "n", 8_499, 600)
    assert inferred_links(Case([a, keep84], []), Options()) == []
    more = leg("b", "m", "n", 10_001, 600)
    assert inferred_links(Case([a, more], []), Options()) == []
    late = leg("b", "m", "n", 9_000, 3 * DAY + 1)
    assert inferred_links(Case([a, late], []), Options()) == []
    before = leg("b", "m", "n", 9_000, -1)
    assert inferred_links(Case([a, before], []), Options()) == []


def test_split_and_alias() -> None:
    a = leg("a", "v", "m", 10_000)
    s1 = leg("s1", "m", "n", 5_000, 600)
    s2 = leg("s2", "m", "o", 4_200, 1200)
    links = inferred_links(Case([a, s1, s2], []), Options())
    assert {(x.a, x.b, x.basis) for x in links} == {("a", "s1", "split"), ("a", "s2", "split")}
    dep = leg("d", "m", "0xdeposit", 9_000, 600, rail="chain")
    out = leg("w", "exch:cust", "z", 8_800, 1800, rail="fedwire")
    case = Case([dep, out], [("0xdeposit", "exch:cust", "exchange reply")])
    assert [(x.a, x.b) for x in inferred_links(case, Options())] == [("d", "w")]
    assert inferred_links(Case([dep, out], []), Options()) == []


def test_threads_mark_breaks() -> None:
    a = leg("a", "v", "c", 10_000, rail="swift", refs={"uetr": U})
    b = leg("b", "c", "m", 10_000, 60, rail="fedwire", refs={"uetr": U})
    c = leg("c", "m", "n", 9_500, 600, rail="rtp")
    lone = leg("z", "p", "q", 7, 5)
    ts = threads(Case([a, b, c, lone], []))
    assert [len(t.legs) for t in ts] == [3, 1]
    assert [(x.a, x.b) for x in ts[0].breaks] == [("b", "c")]
    assert ts[0].rails == ["swift", "fedwire", "rtp"]
    strict = threads(Case([a, b, c, lone], []), Options(min_confidence=0.9))
    assert [len(t.legs) for t in strict] == [2, 1, 1]


@given(
    st.integers(1, 10**9),
    st.integers(0, 100),
    st.integers(1, 3 * DAY),
)
def test_inferred_never_outranks_identifiers(amount: int, keep_pct: int, dt: int) -> None:
    a = leg("a", "v", "m", amount)
    b = leg("b", "m", "n", amount * keep_pct // 100, dt)
    for x in inferred_links(Case([a, b], []), Options()):
        assert x.inferred and 0 < x.confidence <= INFERRED_CAP
