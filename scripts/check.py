#!/usr/bin/env python3
"""Repository content lint.

Runs offline with the standard library only. It looks for things that should
never land in a public repo (credentials, internal names, real-looking contact
details) and for wording we keep out of docs: unbacked compliance or traction
claims and stock filler phrases.

Usage: python3 scripts/check.py
"""

from __future__ import annotations

import ast
import io
import os
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()

# Extra words that must never appear in a published file (for example private
# project names). The list comes from the environment so it is never itself
# published: CHECK_DENY_WORDS="word1,word2". Empty by default, e.g. in CI.
INTERNAL_NEEDLES = tuple(
    w.strip().lower() for w in os.environ.get("CHECK_DENY_WORDS", "").split(",") if w.strip()
)

SECRET_PATTERNS = {
    "aws_access_key_id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key_header": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{10,}\b"),
    "gitlab_token": re.compile(r"\b(?:glpat-|gldt-|glrt-|glptt-)[A-Za-z0-9_\-]{10,}\b"),
    "twilio_api_key": re.compile(r"\bSK[0-9a-fA-F]{32}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
}
INTERNAL_PATH = re.compile("/" + "workspace" + "/|/" + "home" + "/box/")
# The one real address these repos publish, for conduct reports.
PROJECT_EMAILS = frozenset({"opensource@" + "banrox.com"})
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
# RFC 2606 / RFC 6761 names that can never belong to a real person.
RESERVED_DOMAIN = re.compile(
    r"(?i)(^|\.)(example\.(com|net|org)|[a-z0-9-]+\.(test|example|invalid|localhost))$"
)
PHONE = re.compile(
    r"(?<![\w.])(?:\+1(?P<a>\d{3})(?P<b>\d{3})(?P<c>\d{4})"
    r"|(?:\+?1[-. ])?\(?(?P<d>\d{3})\)?[-. ](?P<e>\d{3})[-. ](?P<f>\d{4}))(?![\w.])"
)
PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"
)

POSITIVE_COMPLIANCE = re.compile(r"(?i)\b(soc\s*2|pci(?:[\s-]?dss)?|iso\s*2700\d|fedramp|hipaa)\b")
NEGATION = re.compile(
    r"(?i)\b(not|never|no|don't|do not|doesn't|does not|isn't|is not|neither|nor|without)\b"
)
TRACTION_COUNT = re.compile(
    r"(?i)(?<![\w-])\d[\d,]*\+?\s*(users|customers|downloads|stars|members|companies)\b"
)
TRACTION_PHRASE = re.compile(
    r"(?i)\b(our customers|our users|trusted by|used in production by|in production at"
    r"|battle[- ]tested|thousands of (users|customers)|millions of (users|customers))\b"
)

# Filler and tells we do not want in prose or comments.
STYLE_TELLS = [
    r"\bdelv(e|es|ing)\b",
    r"\brobust(ly|ness)?\b",
    r"\bseamless(ly)?\b",
    r"\bleverag(e|es|ed|ing)\b",
    r"\bcomprehensive\b",
    r"\bin today'?s\b",
    r"\bit'?s (important|worth) (to note|noting)\b",
    r"\bit is (important|worth) (to note|noting)\b",
    r"\bcutting[- ]edge\b",
    r"\bgame[- ]chang",
    r"\bsupercharg",
    r"\bempower",
    r"\btapestry\b",
    r"\bembark",
    r"\bunleash",
    r"\belevate\b",
    r"\bnavigat(e|ing) the (complex|landscape)",
    r"\bever[- ]evolving\b",
    r"\bstate[- ]of[- ]the[- ]art\b",
    r"\bin conclusion\b",
    r"\bas an ai\b",
    r"\blanguage model\b(?! output)",
    r"\b(generated|written) (by|with) (ai|chatgpt|an? llm|claude|copilot|gpt)",
    r"\bco-authored-by\b",
]
STYLE_RE = re.compile("|".join(STYLE_TELLS), re.I)
EMOJI = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\u2705]")
EM_DASH = "\u2014"

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".hypothesis",
    "build",
    "dist",
}
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
    ".sh",
    ".toml",
    ".json",
    ".jsonl",
    ".cfg",
    ".ini",
}
TEXT_NAMES = {"LICENSE", ".gitignore", "Makefile", "Dockerfile"}

errors: list[str] = []


def iter_files() -> list[Path]:
    out = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(p in SKIP_DIRS for p in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES:
            out.append(path)
    return sorted(out)


def phone_is_fictional(m: re.Match[str]) -> bool:
    # 555-0100 through 555-0199 is the reserved fictional range in the NANP.
    exchange = m.group("b") or m.group("e")
    line = m.group("c") or m.group("f")
    return exchange == "555" and line.startswith("01")


def python_prose(text: str) -> list[tuple[int, str]]:
    """Comments and docstrings from a Python source, with line numbers."""
    out: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], tok.string))
    except (tokenize.TokenError, SyntaxError):
        return out
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body:
                start = node.body[0].lineno
                for offset, line in enumerate(doc.splitlines()):
                    out.append((start + offset, line))
    return out


def lint_file(path: Path) -> None:
    rel = path.relative_to(ROOT)
    text = path.read_text(encoding="utf-8", errors="replace")
    is_self = path.resolve() == SELF
    for i, line in enumerate(text.splitlines(), 1):
        lower = line.lower()
        if not is_self and any(n in lower for n in INTERNAL_NEEDLES):
            errors.append(f"{rel}:{i}: internal_name")
        if INTERNAL_PATH.search(line):
            errors.append(f"{rel}:{i}: internal_path")
        if is_self:
            continue
        for kind, pat in SECRET_PATTERNS.items():
            if pat.search(line):
                errors.append(f"{rel}:{i}: {kind}")
        for m in EMAIL.finditer(line):
            if m.group(0).lower() in PROJECT_EMAILS:
                continue
            if not RESERVED_DOMAIN.search(m.group(1)):
                errors.append(f"{rel}:{i}: email_not_reserved_domain")
        for m in PHONE.finditer(line):
            if not phone_is_fictional(m):
                errors.append(f"{rel}:{i}: phone_not_fictional")
        if PRIVATE_IP.search(line):
            errors.append(f"{rel}:{i}: private_ip")
        if POSITIVE_COMPLIANCE.search(line) and not NEGATION.search(line):
            errors.append(f"{rel}:{i}: unsupported_compliance_claim")
        if TRACTION_COUNT.search(line) and not NEGATION.search(line):
            errors.append(f"{rel}:{i}: traction_claim")
        if TRACTION_PHRASE.search(line) and not NEGATION.search(line):
            errors.append(f"{rel}:{i}: traction_claim")

    if is_self:
        return
    if path.suffix == ".md":
        prose = list(enumerate(text.splitlines(), 1))
    elif path.suffix == ".py":
        prose = python_prose(text)
    else:
        prose = [(i, ln) for i, ln in enumerate(text.splitlines(), 1) if ln.lstrip().startswith("#")]
    for i, line in prose:
        m = STYLE_RE.search(line)
        if m:
            errors.append(f"{rel}:{i}: style_tell ({m.group(0).lower()})")
        if EMOJI.search(line):
            errors.append(f"{rel}:{i}: emoji")
        if EM_DASH in line:
            errors.append(f"{rel}:{i}: em_dash")


def lint_skill() -> None:
    path = ROOT / "SKILL.md"
    if not path.is_file():
        errors.append("missing SKILL.md")
        return
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        errors.append("SKILL.md: missing frontmatter")
        return
    meta = dict(
        (k.strip(), v.strip().strip("\"'"))
        for k, v in (ln.split(":", 1) for ln in m.group(1).splitlines() if ":" in ln)
    )
    if meta.get("name") != ROOT.name:
        errors.append(f"SKILL.md: name should be {ROOT.name!r}")
    if len(meta.get("description", "")) < 40:
        errors.append("SKILL.md: description missing or too short")


def lint_license() -> None:
    path = ROOT / "LICENSE"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not text.startswith("MIT License") or "Copyright (c) 2026 Banrox Inc." not in text:
        errors.append("LICENSE: expected MIT, Copyright (c) 2026 Banrox Inc.")


def lint_commits() -> None:
    try:
        log = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--format=%an <%ae>%n%cn <%ce>%n%B"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return
    for line in log.splitlines():
        m = STYLE_RE.search(line)
        if m:
            errors.append(f"git log: style_tell in commit message ({m.group(0).lower()})")
        if any(n in line.lower() for n in INTERNAL_NEEDLES):
            errors.append("git log: internal_name in commit metadata")


def main() -> int:
    lint_skill()
    lint_license()
    for path in iter_files():
        lint_file(path)
    lint_commits()
    if errors:
        print(f"FAIL {ROOT.name}: {len(errors)} issue(s)")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"PASS {ROOT.name} content lint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
