# Sample data — FICTIONAL

Everything in this folder is **invented for software development and testing**. None of it is a policy of The Manipal Group or of any real organisation. "Demo Health Services" does not exist.

These files let ingestion, retrieval and the admin workflow be built and tested before HR provides real, approved policies. Replace them with HR-approved documents for any demonstration to HR or employees.

| File | Purpose |
|---|---|
| `policies/leave-policy-v1.pdf` | Leave types, accrual, how to apply, probation rules |
| `policies/leave-policy-v2.pdf` | Changed version of the same policy (earned leave 18 → 20 days, notice 7 → 10 days) for the policy-replacement demonstration |
| `policies/travel-reimbursement-policy-v1.docx` | Word format; includes a daily-allowance table, claim deadline and required documents |
| `policies/salary-advance-policy-v1.pdf` / `.docx` | Instalment rules and eligibility; same content in both formats to compare the two parsers |

Regenerate them (from `backend/`):

```bash
uv run python scripts/build_sample_policies.py
```

A test fails if any sample stops starting with the "FICTIONAL SAMPLE" banner.
