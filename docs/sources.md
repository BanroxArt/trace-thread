# Sources

Checked 2026-11-16.

| Topic | Source | What we use |
| --- | --- | --- |
| UETR on SWIFT | [Swift, What is a UETR](https://www.swift.com/your-needs/industry-themes/unique-end-to-end-transaction-reference-uetr) | 36 characters, mandatory on MT103, MT202 COV and related; intermediaries must not generate a new UETR and must pass it on; cover payments copy it. |
| UETR on Fedwire | [Fedwire Funds Service ISO 20022 format FAQ](https://www.frbservices.org/resources/financial-services/wires/fedwire-services-frequently-asked-questions/fedwire-service-iso-20022-faq/format-faq/) | UETR mandatory in pacs.008, pacs.009, pacs.004; format checked, uniqueness not; pacs.004 carries the original UETR; camt.056 to request a return, camt.029 to answer. |
| Fedwire casing | [Fedwire market practice for gpi and UETR](https://frbservices.org/wp-content/uploads/fedwire-funds-practice-gpi-uetr.pdf) | Fedwire upper-cases UETRs; compare case-insensitively. |
| ACH trace number | [Treasury Financial Experience, Trace Number](https://tfx.treasury.gov/taxonomy/term/10847) | 15 digits: ODFI routing prefix (8) and item number (7). |
| FedNow tools and messages | [FedNow Service Operating Procedures v3.7, October 2026](https://www.frbservices.org/wp-content/uploads/101326-fednow-service-operating-procedures.pdf) | Return request (camt.056) and payment return (pacs.004); participant negative lists apply per participant. |
| RTP returns | [TCH, RTP Request for Return guidelines](https://www.theclearinghouse.org/-/media/New/TCH/Documents/Payment-Systems/RTP_Request_for_Returns_v02-19-2021.pdf) | Final once accepted; receiver has no obligation to return funds. |
| Recovery in practice | [FBI IC3 2025 Internet Crime Report](https://www.ic3.gov/AnnualReport/Reports/2025_IC3Report.pdf) | Financial Fraud Kill Chain: 3,900 incidents, $1,163,919,846 attempted, $679,013,183 frozen; second-hop recovery depends on the information provided. |
| Stablecoin freezes | [GENIUS Act, Pub. L. 119-27](https://www.congress.gov/119/plaws/publ27/PLAW-119publ27.htm) | Sec. 4(a)(5)(A)(iv) block, freeze and reject capability; lawful orders with reasonable particularity; sec. 20 effective date. |
| Effective date | [OCC final rule 2026-21706, October 23, 2026](https://www.federalregister.gov/documents/2026/10/23/2026-21706/implementing-the-guiding-and-establishing-national-innovation-for-us-stablecoins-act-for-the) | 120 days after it falls after January 18, 2027. |
