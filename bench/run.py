"""Link and simulate on a synthetic case with many mule hops."""

from __future__ import annotations

import random
import time

from tracethread import Case, Scenario, simulate, threads
from tracethread.model import leg_from


def build(n: int, seed: int = 1) -> Case:
    rng = random.Random(seed)
    legs = []
    holders = ["victim"]
    for i in range(n):
        frm = rng.choice(holders[-20:])
        to = f"m{i}"
        legs.append(
            leg_from(
                {
                    "id": f"L{i}",
                    "rail": rng.choice(["rtp", "fednow", "ach", "fedwire"]),
                    "kind": "payment",
                    "ts": 1_772_467_200 + i * 300,
                    "amount": rng.randint(1_000, 50_000) * 100,
                    "currency": "USD",
                    "from_party": frm,
                    "to_party": to,
                    "from_inst": "bank99" if frm == "victim" else f"bank{int(frm[1:]) % 30}",
                    "to_inst": f"bank{i % 30}",
                }
            )
        )
        holders.append(to)
    return Case(legs, [])


def main() -> None:
    for n in (500, 2_000, 10_000):
        case = build(n)
        t0 = time.perf_counter()
        ts = threads(case)
        t1 = time.perf_counter()
        r = simulate(case.legs, {"L0"}, Scenario("x", case.legs[0].ts + 3600, hop_delay=1800))
        t2 = time.perf_counter()
        print(
            f"{n} legs: link {t1 - t0:.2f}s ({len(ts)} threads), "
            f"simulate {t2 - t1:.2f}s, frozen {r.frozen_total}"
        )


if __name__ == "__main__":
    main()
