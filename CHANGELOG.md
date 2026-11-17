# Changelog

## 0.1.0 (2026-11-16)

- `link`: group legs into threads from shared identifiers (UETR, IMAD/OMAD, transaction hash, transaction, end-to-end, instruction and message IDs scoped to the sending agent, ACH trace number with a date window, issuer mint and burn references), returns and recalls that name the original, and inferred pass-through and split links kept separate from identifier links. Markdown, JSON and Mermaid output.
- `check`: format checks for UETR (UUID v4), ACH trace numbers, Fedwire IMAD/OMAD and transaction hashes.
- `simulate`: policy-testing model of recall and hold scenarios (per-hop manual notice, a hypothetical broadcast, per-institution hold delay and return policy) under FIFO, LIFO, haircut and bounding taint rules.
