"""Formats of the payment identifiers the linker reads.

Only the formats a public primary source pins down are validated here:

- UETR: a UUID version 4 (RFC 4122). Fedwire Funds requires one in every
  pacs.008, pacs.009 and pacs.004, checks its format and does not check that
  it is unique. Fedwire upper-cases message text, so UETRs are compared in
  lower case.
- ACH trace number: 15 digits, the ODFI's 8-digit routing prefix followed by a
  7-digit sequence number. The sequence wraps, so a trace number is only
  unique together with its date.
- Fedwire IMAD and OMAD: 8-digit cycle date, 8-character source, 6-digit
  sequence.

FedNow and RTP message and transaction IDs are treated as opaque strings: the
network formats are in participant documentation, and nothing here depends
on their internal structure.
"""

from __future__ import annotations

import datetime as dt
import re

_UETR = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_TRACE = re.compile(r"^\d{15}$")
_IMAD = re.compile(r"^(\d{8})([A-Z0-9]{8})(\d{6})$")


def norm_uetr(v: str) -> str:
    return v.strip().lower()


def uetr_ok(v: str) -> bool:
    return bool(_UETR.match(norm_uetr(v)))


def ach_trace_ok(v: str) -> bool:
    return bool(_TRACE.match(v.strip()))


def ach_odfi(v: str) -> str:
    """The 8-digit ODFI routing prefix of a trace number."""
    if not ach_trace_ok(v):
        raise ValueError(f"not a 15-digit ACH trace number: {v!r}")
    return v.strip()[:8]


def imad_ok(v: str) -> bool:
    m = _IMAD.match(v.strip().upper())
    if not m:
        return False
    try:
        dt.datetime.strptime(m.group(1), "%Y%m%d")
    except ValueError:
        return False
    return True


def norm(kind: str, v: str) -> str:
    """Normal form for comparing two identifiers of the same kind."""
    v = v.strip()
    if kind in ("uetr", "orig_uetr"):
        return norm_uetr(v)
    if kind in ("imad", "omad", "orig_imad"):
        return v.upper()
    if kind in ("tx_hash", "token"):
        return v.lower()
    return v


def check(kind: str, v: str) -> str | None:
    """A problem with the identifier's format, or None."""
    if kind in ("uetr", "orig_uetr") and not uetr_ok(v):
        return "UETR is not a UUID version 4"
    if kind in ("ach_trace", "orig_ach_trace") and not ach_trace_ok(v):
        return "ACH trace number is not 15 digits"
    if kind in ("imad", "omad", "orig_imad") and not imad_ok(v):
        return "IMAD/OMAD is not YYYYMMDD + 8-character source + 6-digit sequence"
    if kind == "tx_hash" and not re.fullmatch(r"0x[0-9a-fA-F]{64}", v):
        return "transaction hash is not 32 bytes of hex"
    return None
