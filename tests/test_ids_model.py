from __future__ import annotations

import pytest

from tracethread import LegError, case_from
from tracethread.ids import ach_odfi, ach_trace_ok, check, imad_ok, uetr_ok
from tracethread.model import parse_ts

U = "eb6305c9-1f7f-49de-aed0-16487c27b42d"  # the example in the Fedwire gpi market practice


def test_uetr() -> None:
    assert uetr_ok(U) and uetr_ok(U.upper())
    assert not uetr_ok(U.replace("-49de-", "-39de-"))  # version 3
    assert not uetr_ok(U.replace("-aed0-", "-ced0-"))  # wrong variant
    assert not uetr_ok(U[:-1])


def test_ach_trace() -> None:
    assert ach_trace_ok("061112840000001")
    assert ach_odfi("061112840000001") == "06111284"
    assert not ach_trace_ok("06111284000001")
    with pytest.raises(ValueError):
        ach_odfi("x")


def test_imad() -> None:
    assert imad_ok("20260302QMGFT015000012")
    assert not imad_ok("20260230QMGFT015000012")  # no 30 February
    assert not imad_ok("20260302QMGFT01500012")
    assert check("imad", "bad") and check("uetr", "bad") and check("tx_hash", "0x12")
    assert check("e2e_id", "anything") is None


def test_timestamps_need_offsets() -> None:
    assert parse_ts("2026-03-02T16:00:00Z") == 1_772_467_200
    assert parse_ts("2026-03-02T08:00:00-08:00") == 1_772_467_200
    with pytest.raises(LegError):
        parse_ts("2026-03-02T16:00:00")
    with pytest.raises(LegError):
        parse_ts(True)


BASE = {
    "id": "a",
    "rail": "rtp",
    "kind": "payment",
    "ts": 1,
    "amount": 5,
    "currency": "usd",
    "from_party": "x",
    "to_party": "y",
}


@pytest.mark.parametrize(
    "change",
    [
        {"rail": "telegraph"},
        {"kind": "gift"},
        {"amount": -1},
        {"amount": 1.5},
        {"amount": True},
        {"refs": {"serial_number": "1"}},
        {"refs": []},
        {"colour": "red"},
    ],
)
def test_bad_legs(change: dict[str, object]) -> None:
    with pytest.raises(LegError):
        case_from([{**BASE, **change}])


def test_case_rules() -> None:
    c = case_from([BASE])
    assert c.legs[0].currency == "USD"
    with pytest.raises(LegError):
        case_from([BASE, BASE])
    with pytest.raises(LegError):
        case_from({"legs": [BASE], "aliases": [{"a": "x", "b": "y"}]})
    with pytest.raises(LegError):
        case_from({"nope": 1})
    with pytest.raises(LegError):
        case_from([{k: v for k, v in BASE.items() if k != "to_party"}])
