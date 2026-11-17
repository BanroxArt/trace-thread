# trace-thread

Put the legs of one payment back in order when it crossed rails, and see which links are proven by a shared identifier and which are guesses. Then test what a faster recall or a different hold policy would have recovered, on a model.

A business email compromise payment can leave the victim's bank as a SWIFT message, reach the beneficiary bank over Fedwire, leave the mule's account the same hour by RTP and FedNow, become a stablecoin through an issuer's mint, and land at an exchange. Every institution on the way has its own record with its own identifiers. `trace-thread` reads those records as legs, links them, and says where the identifier trail breaks, which is where an investigator has to go and ask.

Built and maintained by Art Akopian, CEO of [Banrox](https://banrox.com).

> **Engineering checklist, not legal advice.** The linker shows which records share identifiers; it does not establish who owns an account, who is liable, or what a court would accept. The simulator is a model for comparing policies under assumptions you choose. It does not describe how any network or bank behaves today. Tested on synthetic data only: every case, party, institution and identifier in this repository is made up.

## Why

FBI IC3's Recovery Asset Team runs the Financial Fraud Kill Chain with banks. In 2025 it took 3,900 incidents with $1,163,919,846 in attempted losses and froze $679,013,183, 58% ([IC3 2025 report](https://www.ic3.gov/AnnualReport/Reports/2025_IC3Report.pdf)). The same report notes that funds that have moved on to a second account can be pursued only if that information is provided. Recovery is a race between the money moving and someone at the next institution hearing about it, and both depend on knowing where the money went.

Identifiers help less than people expect:

- A **UETR** is mandatory in SWIFT payment messages and, since July 2025, in every Fedwire Funds pacs.008, pacs.009 and pacs.004. Intermediaries must pass it on unchanged. It follows *one* payment from ordering bank to beneficiary bank. When the beneficiary pays someone else, that is a new payment with a new UETR. Fedwire checks the format but not uniqueness, and upper-cases it.
- An **ACH trace number** is 15 digits, the ODFI's 8-digit routing prefix and a 7-digit sequence. The sequence wraps, so a trace number identifies an entry only together with its date.
- **End-to-end, instruction and transaction IDs** are set by a party in the chain and are unique only for that party. The linker scopes them to the sending agent.
- **Returns and recalls** name the original: a Fedwire pacs.004 carries the original UETR, a camt.056 return request names the payment it asks to return.
- **Stablecoin mint and burn** carry no bank payment identifier. We found no standard that carries a UETR or an end-to-end ID through a mint or a burn. The link from a wire into an issuer's reserve account to a mint exists only in the issuer's own records; `issuer_ref` is where you put what the issuer told you.

## Link

```sh
pip install 'tracethread @ git+https://github.com/BanroxArt/trace-thread'
tracethread check examples/case.json
tracethread link examples/case.json                  # Markdown timeline per thread
tracethread link examples/case.json --format json
tracethread link examples/case.json --format mermaid
```

A leg is one movement of value as one institution recorded it:

```json
{"id": "L1F", "rail": "fedwire", "kind": "payment", "ts": "2026-03-02T16:11:00Z",
 "amount": 25000000, "currency": "USD",
 "from_party": "corr-c:nostro", "to_party": "mule1:dda",
 "from_inst": "Correspondent C", "to_inst": "Bank B",
 "refs": {"uetr": "6513270E-269E-4D37-B2A7-4DE452E6B438", "imad": "20260302QMGFT015000012"}}
```

Rails: swift, fedwire, chips, ach, fednow, rtp, p2p, book, card, chain, cash, other. Kinds: payment, return, recall_request, mint, burn, transfer. Amounts are integers in minor units; timestamps need a UTC offset.

| link | basis | confidence |
|---|---|---|
| same UETR, IMAD, OMAD or transaction hash | identifier | 1.0 |
| return or recall naming the original (`orig_uetr`, `orig_tx_id`, `orig_ach_trace` ...) | identifier | 1.0 |
| same ACH trace number within 5 days | identifier | 0.95 |
| same issuer reference on a fiat leg and a mint or burn | issuer's records | 0.95 |
| same transaction, end-to-end, instruction or message ID from the same sending agent | identifier | 0.8 to 0.9 |
| value lands with a holder and 85% to 100% of it leaves within 3 days | inferred | at most 0.7 |
| several outflows soon after one credit together move most of it | inferred | at most 0.6 |

Inferred links are listed as **breaks**: places where only amounts and timing join two legs. Aliases (`"aliases": [{"a": "0xbb..", "b": "exchange-y:cust-77", "basis": "..."}]`) let you state that two identifiers belong to one holder, with who said so. Without an alias the linker never assumes it.

## Simulate recall and hold policies

```sh
tracethread simulate examples/case.json examples/policies.toml
```

On the example case (a $250,000 invoice payment split across RTP and FedNow, one leg minted into a stablecoin):

| scenario | frozen | returned | not recovered |
|---|---|---|---|
| manual recall, 4h per hop, stops after 2 hops | 15,000.00 | 15,000.00 | 235,000.00 |
| manual recall, 30m per hop | 250,000.00 | 130,000.00 | 120,000.00 |
| hypothetical: every receiving bank hears in 5m | 250,000.00 | 250,000.00 | 0.00 |
| reported within the hour, 15m per hop | 250,000.00 | 250,000.00 | 0.00 |

A scenario sets when the fraud was reported, how notice travels, and what each institution does:

- `mode = "chain"`: notice moves one hop at a time, `hop_delay` per hop, from the institution that sent tainted value to the one that received it, optionally stopping after `max_hops`. This is closest to how recalls work now.
- `mode = "broadcast"`: every institution that received tainted value hears after `broadcast_delay`. **Hypothetical.** No network does this today; it is there to measure what such a thing would be worth.
- Per institution: `responds`, `hold_delay` (time from notice to hold; for a stablecoin issuer, the time to a lawful order or its own decision) and `returns` (a hold is not a return).
- `method`: `fifo`, `lifo`, `haircut` (proportional), and `tainted_first` / `clean_first` as upper and lower bounds.

A hold freezes the tainted balance at that moment and any tainted value that arrives later; clean value stays spendable. Outflows the case cannot fund are treated as money from outside the case, the same way in every scenario.

## What is real and what is not

Checked against primary sources in November 2026.

- **Fraud flags do not propagate on their own.** A FedNow participant's negative list applies to that participant's own payments and is not shared with other participants ([FedNow Operating Procedures v3.7](https://www.frbservices.org/wp-content/uploads/101326-fednow-service-operating-procedures.pdf)). On RTP and FedNow, a fraud report goes to the network and to the other bank in that payment. The next bank hears only if someone sends a recall, an FFKC referral or a 314(b) request. That is why `chain` is the default and `broadcast` is labelled hypothetical.
- **Recall is a request.** Fedwire customers request a return with camt.056 and answer with camt.029 ([Fedwire format FAQ](https://www.frbservices.org/resources/financial-services/wires/fedwire-services-frequently-asked-questions/fedwire-service-iso-20022-faq/format-faq/)). TCH's RTP guidelines say a payment is final once accepted and the receiving bank has no obligation to return funds ([RTP Request for Return guidelines](https://www.theclearinghouse.org/-/media/New/TCH/Documents/Payment-Systems/RTP_Request_for_Returns_v02-19-2021.pdf)).
- **"Tokens carry the UETR through mint and burn":** not supported by any standard we found. Treat it as unverified.
- **Stablecoin freezes** need the issuer's own policy decision or a lawful order. The GENIUS Act (Pub. L. 119-27) requires permitted issuers to have the technical ability to block, freeze and reject transactions that violate law (sec. 4(a)(5)(A)(iv)), and a lawful order must name the coins or accounts with reasonable particularity. It sets no velocity limit or cooling-off period. The Act takes effect on January 18, 2027, the 18-month date, because 120 days after the OCC's implementing rule (published October 23, 2026) falls later ([OCC final rule](https://www.federalregister.gov/documents/2026/10/23/2026-21706/implementing-the-guiding-and-establishing-national-innovation-for-us-stablecoins-act-for-the)).
- **A stablecoin unit is not a serial-numbered note.** ERC-20 tokens are balances. Following "the" stolen dollar through a mixed account needs an accounting rule, which is why the simulator makes you pick one and shows the spread between them.

## Limits

- The linker sees only what you give it. Most real cases have gaps where a record was never obtained.
- Inferred links are leads. Two unrelated payments of similar size an hour apart will be linked if they share a holder.
- The simulator has no fees, FX or partial returns beyond what the legs show, and one unit of account per run (`par` lets you declare USD and dollar stablecoins equal).
- No identifier format beyond UETR, ACH trace, IMAD/OMAD and transaction hash is validated, because FedNow and RTP ID formats are in participant documentation.

## Development

```sh
pip install -e '.[dev]'
make check     # ruff, content lint, mypy --strict, pytest (Hypothesis included)
make bench
```

[docs/sources.md](docs/sources.md) lists every source. [docs/benchmarks.md](docs/benchmarks.md) has timings.

## License

MIT, Copyright (c) 2026 Banrox Inc.
