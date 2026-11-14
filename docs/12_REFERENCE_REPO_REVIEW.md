# 12 · Reference repository data review

Reviewed to identify reusable test data for PayeeTrail. No external vendor records or documents were copied into this project.

| Repository | Data found | Fit and reuse decision |
|---|---|---|
| [Automated Vendor Risk Assessment](https://github.com/austinsonger/Automated-Vendor-Risk-Assessment) | A Google Workspace assessment example; no PAN, GSTIN, bank proof, or document test corpus surfaced. Its README states MIT. | Useful as a broad risk-assessment example, not as KYC fixtures. |
| [Vendor Due Diligence Tool](https://github.com/YashKutehub/vendor-due-diligence-tool) | Twelve preloaded Indian companies. Its README says the company details and CINs are real public data; it does not provide identity or bank proof PDFs. | Do not load these records into the synthetic vendor master. Real public companies are not interchangeable with fictitious vendors, and public data may become stale. |
| [MOSIP](https://github.com/mosip) | Registration and test automation data, focused on identity enrollment packets, operators, and biometrics. MOSIP documents MPL 2.0 licensing. | Useful for workflow, retry, status, integrity, and audit patterns. Not appropriate as PayeeTrail vendor data; do not reuse identity packets or biometric fixtures. |
| [LT-VRM](https://github.com/learntprm-design/lt-vrm) | README advertises a 52-vendor demo dataset with documents, contracts, assessments, and scores. The repository lists an MIT license. | Closest source for broad lifecycle UI examples, but its demo data is not identified there as synthetic and is not an Indian PAN/GST/bank-proof corpus. Do not import until the seed records and document provenance have been checked. |
| [Awesome TPRM](https://github.com/ishandutta2007/Awesome-Third-Party-Risk-Management) | Curated links and tool categories; no test corpus. The list is MIT licensed. | Use as a feature roadmap, not as application fixtures. |

## PayeeTrail test data to use now

The project already contains six deterministic scenarios, seventeen scenario PDFs, a separate generated image-only scan PDF, and a six-row vendor master. The README and assumptions document identify these as synthetic; the generated documents have structurally valid identifiers and bank prefixes. They are safer and more directly relevant to the assignment than the external repositories' datasets.

For the OpenRouter demo, run the existing synthetic PDFs through the optional reviewer. A future OCR-specific evaluation set should add generated image-only versions plus rotated, blurred, multi-page, duplicate, wrong-type, and conflicting-field samples. Keep expected values and source pages in a manifest so extraction accuracy can be reviewed field by field.

## Provenance rule

Use generated or clearly licensed synthetic fixtures for demos. Keep real public-company facts separate from identity proof, and record each fixture's source, license, expected fields, and intended edge case.
