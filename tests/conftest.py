from __future__ import annotations

from typing import Any

from tracethread import Leg
from tracethread.model import leg_from

T0 = 1_772_467_200  # 2026-03-02T16:00:00Z


def leg(id: str, frm: str, to: str, amount: int, dt: int = 0, **kw: Any) -> Leg:
    d: dict[str, Any] = {
        "id": id,
        "rail": kw.pop("rail", "rtp"),
        "kind": kw.pop("kind", "payment"),
        "ts": T0 + dt,
        "amount": amount,
        "currency": kw.pop("currency", "USD"),
        "from_party": frm,
        "to_party": to,
        "from_inst": kw.pop("from_inst", f"bank-{frm}"),
        "to_inst": kw.pop("to_inst", f"bank-{to}"),
    }
    d.update(kw)
    return leg_from(d)
