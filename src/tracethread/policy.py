"""Scenario files for the taint simulator (TOML)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .model import parse_ts
from .taint import METHODS, InstPolicy, Method, Scenario

_DUR = re.compile(r"^(\d+)([smhd])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class PolicyError(ValueError):
    pass


def duration(v: Any, what: str) -> int:
    if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
        return v
    if isinstance(v, str):
        m = _DUR.match(v.strip())
        if m:
            return int(m.group(1)) * _UNIT[m.group(2)]
    raise PolicyError(f"{what}: expected seconds or a duration like 30m, 4h, 2d (got {v!r})")


def _inst(d: Any, where: str, base: InstPolicy) -> InstPolicy:
    if not isinstance(d, dict):
        raise PolicyError(f"{where}: expected a table")
    unknown = set(d) - {"responds", "hold_delay", "returns"}
    if unknown:
        raise PolicyError(f"{where}: unknown keys {sorted(unknown)}")
    for k in ("responds", "returns"):
        if k in d and not isinstance(d[k], bool):
            raise PolicyError(f"{where}.{k}: expected true or false")
    return InstPolicy(
        responds=d.get("responds", base.responds),
        hold_delay=duration(d["hold_delay"], f"{where}.hold_delay") if "hold_delay" in d else base.hold_delay,
        returns=d.get("returns", base.returns),
    )


@dataclass(frozen=True)
class PolicyFile:
    seeds: set[str]
    par: frozenset[str]
    scenarios: list[Scenario]


_SC_KEYS = {
    "name",
    "report",
    "mode",
    "hop_delay",
    "broadcast_delay",
    "max_hops",
    "method",
    "default",
    "institutions",
}


def policy_from(raw: dict[str, Any]) -> PolicyFile:
    unknown = set(raw) - {"seeds", "par", "scenario"}
    if unknown:
        raise PolicyError(f"unknown top-level keys {sorted(unknown)}")
    seeds = raw.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        raise PolicyError("seeds: list the leg ids the victim reported")
    scs = raw.get("scenario")
    if not isinstance(scs, list) or not scs:
        raise PolicyError("add at least one [[scenario]]")
    out = []
    for n, s in enumerate(scs):
        where = f"scenario[{n}]"
        if not isinstance(s, dict):
            raise PolicyError(f"{where}: expected a table")
        bad = set(s) - _SC_KEYS
        if bad:
            raise PolicyError(f"{where}: unknown keys {sorted(bad)}")
        if "name" not in s or "report" not in s:
            raise PolicyError(f"{where}: name and report are required")
        mode = s.get("mode", "chain")
        if mode not in ("chain", "broadcast", "none"):
            raise PolicyError(f"{where}.mode: chain, broadcast or none")
        method = s.get("method", "fifo")
        if method not in METHODS:
            raise PolicyError(f"{where}.method: one of {', '.join(METHODS)}")
        max_hops = s.get("max_hops")
        bad_hops = not isinstance(max_hops, int) or isinstance(max_hops, bool) or max_hops < 0
        if max_hops is not None and bad_hops:
            raise PolicyError(f"{where}.max_hops: a non-negative integer")
        default = _inst(s.get("default", {}), f"{where}.default", InstPolicy())
        insts = s.get("institutions", {})
        if not isinstance(insts, dict):
            raise PolicyError(f"{where}.institutions: expected a table")
        try:
            report = parse_ts(s["report"])
        except ValueError as e:
            raise PolicyError(f"{where}.report: {e}") from None
        out.append(
            Scenario(
                name=str(s["name"]),
                report_ts=report,
                mode=mode,
                hop_delay=duration(s.get("hop_delay", "4h"), f"{where}.hop_delay"),
                broadcast_delay=duration(s.get("broadcast_delay", "5m"), f"{where}.broadcast_delay"),
                max_hops=max_hops,
                method=cast(Method, method),
                default=default,
                institutions={
                    str(k): _inst(v, f"{where}.institutions.{k}", default) for k, v in insts.items()
                },
            )
        )
    return PolicyFile({str(x) for x in seeds}, frozenset(str(x).upper() for x in raw.get("par", [])), out)


def load_policy(path: str | Path) -> PolicyFile:
    try:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise PolicyError(f"{path}: {e}") from None
    return policy_from(raw)
