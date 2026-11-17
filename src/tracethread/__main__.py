"""Command line: check, link, simulate."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .link import Options, threads
from .model import LegError, load_case
from .policy import PolicyError, load_policy
from .render import link_json, mermaid, results_md, thread_md
from .taint import SimError, simulate

DISCLAIMER = "Engineering checklist, not legal advice. Tested on synthetic data only."


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tracethread", description="Link payment legs; test recall policies.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check identifier formats in a case file")
    c.add_argument("case")
    lk = sub.add_parser("link", help="group legs into threads")
    lk.add_argument("case")
    lk.add_argument("--format", choices=["md", "json", "mermaid"], default="md")
    lk.add_argument("--min-confidence", type=float, default=0.5)
    lk.add_argument("--window", type=int, default=3 * 86_400, help="pass-through window, seconds")
    lk.add_argument("--max-haircut", type=int, default=15, help="percent kept back by a pass-through hop")
    sm = sub.add_parser("simulate", help="run recall and hold scenarios (policy-testing model)")
    sm.add_argument("case")
    sm.add_argument("policy")
    sm.add_argument("--format", choices=["md", "json"], default="md")
    a = p.parse_args(argv)
    try:
        case = load_case(a.case)
        if a.cmd == "check":
            probs = case.format_problems()
            for leg_id, kind, why in probs:
                print(f"{leg_id}: {kind}: {why}")
            print(f"{len(case.legs)} legs, {len(probs)} format problems")
            return 2 if probs else 0
        if a.cmd == "link":
            opts = Options(a.window, a.max_haircut, min_confidence=a.min_confidence)
            ts = threads(case, opts)
            if a.format == "json":
                doc = {
                    "threads": [
                        {
                            "legs": [leg.id for leg in t.legs],
                            "rails": t.rails,
                            "links": [link_json(x) for x in t.links],
                            "breaks": [link_json(x) for x in t.breaks],
                        }
                        for t in ts
                    ],
                    "note": DISCLAIMER,
                }
                print(json.dumps(doc, indent=2))
            elif a.format == "mermaid":
                for t in ts:
                    if len(t.legs) > 1:
                        print(mermaid(t))
            else:
                print("# Payment threads\n")
                for n, t in enumerate(ts, 1):
                    print(thread_md(n, t))
                print(DISCLAIMER)
            return 0
        pol = load_policy(a.policy)
        results = [simulate(case.legs, pol.seeds, sc, pol.par) for sc in pol.scenarios]
        if a.format == "json":
            out = [
                {
                    "scenario": r.scenario,
                    "reported": r.seeded,
                    "frozen": r.frozen,
                    "returned": r.returned,
                    "not_recovered": r.unrecovered,
                    "blocked": r.blocked,
                    "notices": r.notices,
                    "unfunded": r.unfunded,
                }
                for r in results
            ]
            print(json.dumps({"model": "policy-testing", "results": out, "note": DISCLAIMER}, indent=2))
        else:
            print(results_md(results))
            print(DISCLAIMER)
        return 0
    except (OSError, LegError, PolicyError, SimError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
