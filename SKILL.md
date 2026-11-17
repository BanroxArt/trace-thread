---
name: trace-thread
description: Link the legs of a payment that crossed rails (SWIFT, Fedwire, CHIPS, ACH, FedNow, RTP, book transfers, stablecoin mint, transfer and burn) into threads using UETRs, IMAD/OMAD, end-to-end and transaction IDs, ACH trace numbers and issuer references, show where the identifier trail breaks, and compare recall and hold policies on a taint model. Use when an investigator has records of a fraud or recall case from several institutions, or a fraud or payments team wants to test what a faster recall or a hold policy would recover. Uses the tracethread package from this repo. Engineering checklist only, not legal advice.
---

# trace-thread

You help someone put a payment's legs in order and see which links are proven by a shared identifier and which are guesses. You do not decide who is liable, and the simulator is a model for comparing policies, not a statement of how any network behaves.

## 1. Build the case file

- One JSON leg per movement of value: rail, kind (payment, return, recall_request, mint, burn, transfer), time with a UTC offset, amount in minor units, from and to party, from and to institution, and every reference the record shows.
- Use made-up or masked party names in anything you share. Never paste a real customer's account number into a public place.
- If an exchange or another bank told the user that two identifiers are the same holder (a deposit address and a customer account), add it as an alias with the basis: who said so and how.

## 2. Link

- `tracethread check case.json` first; fix any malformed UETR or IMAD before linking.
- `tracethread link case.json` for the timeline, `--format mermaid` for a diagram.
- Read the "trail breaks" list out loud. Each break is a point where the user needs records from the holding institution (a 314(b) request, a subpoena, an exchange's compliance team) before relying on the link.

## 3. Simulate policies

- Write scenarios in TOML (see examples/policies.toml): when the fraud was reported, how notice travels (chain with a delay per hop, or the hypothetical broadcast), who holds, after how long, and who returns.
- Present the output as "under these assumptions". Do not tell the user that fraud reports propagate between banks automatically, that FedNow negative lists are shared, or that a stablecoin issuer freezes without its own policy decision or a lawful order. None of those is true today.

End with: engineering checklist, not legal advice; tested on synthetic data only.
