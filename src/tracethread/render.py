"""Plain-text outputs: a Markdown timeline per thread, a Mermaid graph, and a
table comparing simulated policies."""

from __future__ import annotations

import datetime as dt
from typing import Any

from .link import Link, Thread
from .model import Leg
from .taint import Result


def ts(t: int) -> str:
    return dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def money(n: int) -> str:
    return f"{n / 100:,.2f}"


def _refs(leg: Leg) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(leg.refs.items())) or "none"


def thread_md(n: int, t: Thread) -> str:
    lines = [f"## Thread {n}: {len(t.legs)} legs across {', '.join(t.rails)}", ""]
    lines.append("| time (UTC) | leg | rail | kind | amount | from | to | identifiers |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for leg in t.legs:
        lines.append(
            f"| {ts(leg.ts)} | {leg.id} | {leg.rail} | {leg.kind} | {money(leg.amount)} {leg.currency} "
            f"| {leg.from_party} ({leg.from_inst or '?'}) | {leg.to_party} ({leg.to_inst or '?'}) "
            f"| {_refs(leg)} |"
        )
    lines += ["", "Links:", ""]
    for link in t.links:
        tag = "inferred" if link.inferred else "identifier"
        lines.append(f"- {link.a} -> {link.b}: {link.basis} ({tag}, {link.confidence:.2f}) {link.detail}")
    if t.breaks:
        lines += [
            "",
            "Where the identifier trail breaks (only an inferred link joins these legs; "
            "confirm with the holding institution before relying on it):",
            "",
        ]
        lines += [f"- {b.a} -> {b.b}" for b in t.breaks]
    return "\n".join(lines) + "\n"


def mermaid(t: Thread) -> str:
    out = ["flowchart LR"]
    for leg in t.legs:
        label = f"{leg.id}<br/>{leg.rail} {money(leg.amount)} {leg.currency}"
        out.append(f'  {_node(leg.id)}["{label}"]')
    for link in t.links:
        arrow = "-.->" if link.inferred else "-->"
        out.append(f"  {_node(link.a)} {arrow}|{link.basis}| {_node(link.b)}")
    return "\n".join(out) + "\n"


def _node(s: str) -> str:
    return "n_" + "".join(c if c.isalnum() else "_" for c in s)


def link_json(link: Link) -> dict[str, Any]:
    return {
        "from": link.a,
        "to": link.b,
        "basis": link.basis,
        "confidence": link.confidence,
        "inferred": link.inferred,
        "detail": link.detail,
    }


def results_md(results: list[Result]) -> str:
    lines = [
        "Policy-testing model on the legs given. It shows what each set of assumptions would recover; "
        "it does not describe what any network or bank does today.",
        "",
        "| scenario | reported | frozen | returned | not recovered | outflows blocked |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.scenario} | {money(r.seeded)} | {money(r.frozen_total)} | {money(r.returned)} "
            f"| {money(r.unrecovered)} | {money(r.blocked)} |"
        )
    for r in results:
        lines += ["", f"### {r.scenario}", ""]
        if not r.notices:
            lines.append("No institution is notified in this scenario.")
        for inst, t in r.notices.items():
            lines.append(f"- {inst} hears at {ts(t)}; frozen {money(r.frozen.get(inst, 0))}")
        if r.unfunded:
            lines.append(
                f"- {money(r.unfunded)} of outflows had no visible funding in the case and were treated as "
                "clean money from outside it."
            )
    return "\n".join(lines) + "\n"
