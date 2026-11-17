from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracethread import PolicyError, load_case, load_policy, policy_from, simulate
from tracethread.__main__ import main

EX = Path(__file__).resolve().parents[1] / "examples"


def test_example_policies_load_and_differ() -> None:
    pol = load_policy(EX / "policies.toml")
    case = load_case(EX / "case.json")
    res = {sc.name: simulate(case.legs, pol.seeds, sc, pol.par) for sc in pol.scenarios}
    returned = [r.returned for r in res.values()]
    assert returned == sorted(returned) and returned[0] < returned[-1]
    slow = res["manual recall, 4h per hop, stops after 2 hops"]
    assert set(slow.notices) == {"Correspondent C", "Bank B"}
    assert res["manual recall, 30m per hop"].frozen["Bank C"] == 12_000_000


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"seeds": ["L1"]},
        {"seeds": [], "scenario": [{"name": "x", "report": 0}]},
        {"seeds": ["L1"], "scenario": [{"name": "x"}]},
        {"seeds": ["L1"], "scenario": [{"name": "x", "report": 0, "mode": "telepathy"}]},
        {"seeds": ["L1"], "scenario": [{"name": "x", "report": 0, "method": "lucky"}]},
        {"seeds": ["L1"], "scenario": [{"name": "x", "report": 0, "hop_delay": "soon"}]},
        {"seeds": ["L1"], "scenario": [{"name": "x", "report": 0, "max_hops": -1}]},
        {"seeds": ["L1"], "scenario": [{"name": "x", "report": "yesterday"}]},
        {"seeds": ["L1"], "scenario": [{"name": "x", "report": 0, "default": {"returns": "yes"}}]},
        {"seeds": ["L1"], "scenario": [{"name": "x", "report": 0, "institutions": {"B": {"speed": 1}}}]},
        {"seeds": ["L1"], "scenario": [{"name": "x", "report": 0, "colour": 1}]},
        {"seeds": ["L1"], "extra": 1, "scenario": [{"name": "x", "report": 0}]},
    ],
)
def test_bad_policies(raw: dict[str, object]) -> None:
    with pytest.raises(PolicyError):
        policy_from(raw)


def test_institution_inherits_default() -> None:
    pol = policy_from(
        {
            "seeds": ["L1"],
            "scenario": [
                {
                    "name": "x",
                    "report": 0,
                    "default": {"hold_delay": "1h", "returns": False},
                    "institutions": {"B": {"returns": True}},
                }
            ],
        }
    )
    b = pol.scenarios[0].policy("B")
    assert b.hold_delay == 3600 and b.returns and not pol.scenarios[0].policy("Z").returns


def test_cli(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    case, pol = str(EX / "case.json"), str(EX / "policies.toml")
    assert main(["check", case]) == 0
    assert main(["link", case]) == 0
    out = capsys.readouterr().out
    assert "Where the identifier trail breaks" in out and "synthetic data only" in out
    assert main(["link", case, "--format", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert len(doc["threads"][0]["legs"]) == 9
    assert main(["link", case, "--format", "mermaid"]) == 0
    assert "flowchart LR" in capsys.readouterr().out
    assert main(["simulate", case, pol]) == 0
    assert "Policy-testing model" in capsys.readouterr().out
    assert main(["simulate", case, pol, "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["model"] == "policy-testing"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"id": "a", "rail": "x"}]))
    assert main(["link", str(bad)]) == 1
    fmt = tmp_path / "fmt.json"
    fmt.write_text(
        json.dumps(
            [
                {
                    "id": "a",
                    "rail": "fedwire",
                    "kind": "payment",
                    "ts": 0,
                    "amount": 1,
                    "currency": "USD",
                    "from_party": "x",
                    "to_party": "y",
                    "refs": {"uetr": "not-a-uuid"},
                }
            ]
        )
    )
    assert main(["check", str(fmt)]) == 2
