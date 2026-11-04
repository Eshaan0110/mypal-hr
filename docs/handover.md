# My Pal: handover

The state of the My Pal prototype at the end of the planned build (phases 0–9). It covers what exists, what is still waiting on HR and IT, the risks of running it, and what would have to change before production. The prototype is **not production-ready**, and nothing in this repository claims otherwise.

## 1. Where to start

| Read | For |
|---|---|
| [README.md](../README.md) | What My Pal is, the status of each phase, quick start |
| [operations.md](operations.md) | Setup, configuration, migrations, loading policies, tests, backup, update, rollback |
| [backend/README.md](../backend/README.md) | API, answer pipeline, ingestion, HR administration, data model, code conventions |
| [frontend/README.md](../frontend/README.md) | Chat interface and HR admin portal |
| [security-and-evaluation.md](security-and-evaluation.md) | Threats, controls, the tests that prove them, evaluation results, known limitations |
| [backend/eval/README.md](../backend/eval/README.md) | Retrieval and answer evaluation sets, results and the decisions they led to |
| `My_Pal_Technical_Design.docx` | Design document written for IT before phases 7–9. Where it differs, the Markdown documents above describe the current state. |

## 2. What the prototype does

- **Employee chat:**
  - answers HR policy questions only from approved, active, in-effect policy versions that apply to the employee's company, location and category;
  - cites policy, version, section, page, effective date and link;
  - asks a clarification question when context is missing;
  - otherwise refers the employee to HR, with a reason.
- **Answer safety:** citations are built from the database. Every number in an answer must appear in a cited passage. Personal-record questions are referred directly, and sensitive topics always show the confidential route.
- **HR admin portal:** upload (PDF or Word), parsed preview with a quality report, submit, approve by a second administrator, reject, publish, replace, and restore (rollback), with an append-only audit trail.
- **Search:** hybrid dense and BM25 search with reciprocal rank fusion and a cross-encoder reranker, filtered by scope inside Qdrant and re-checked against Postgres.
- **Privacy:** feedback and metrics store no question text, answer text or user identity.
- **Evidence:**
  - 265 backend and 23 frontend automated tests;
  - stress and failure testing, with every problem it found fixed (security-and-evaluation.md §6);
  - security tests organised by threat;
  - retrieval and whole-answer evaluation tools;
  - a reproducible Docker setup, verified on a fresh copy.

Evaluation results are in [security-and-evaluation.md](security-and-evaluation.md):
- On the 41-question fictional set: 38 pass, 3 partial, 0 unsafe.
- On the 98 questions supplied with the first business unit's real policies: 81 correct, 13 partial, 2 incorrect, 2 missed (graded by hand, run 3).

## 3. Decisions and where they came from

| Source | Decisions |
|---|---|
| **Reference documents** (concept note, implementation plan) | RAG answering from approved policies only; citations; clarification and HR referral; scope by company, location and category; HR admin portal with review and publication; versioning and audit; no identifiable chat history by default; about 100 evaluation questions; one business unit, 3–5 policies |
| **Company IT** | IT intends to host the language model on its GPUs behind an OpenAI-compatible endpoint. Identity provider, secret store, hosting and Git remote: **not yet decided** (section 4) |
| **Our technical choices** (explained in each phase report) | uv and Python 3.11; FastAPI; PostgreSQL with SQLAlchemy and Alembic; Qdrant; hybrid search with RRF and a MiniLM reranker (chosen by measurement); `bge-small` embeddings; four-eyes approval enforced by a database CHECK; append-only audit trigger; React, Vite and Tailwind; Docker Compose |
| **Temporary development compromises** | Development login stand-in (`X-Dev-User`); Ollama `qwen3.5:9b` on a laptop; `.env` files for secrets; fictional sample policies and scope codes; single machine, no high availability |

## 4. Outstanding approvals and inputs

Nothing below can be settled in code alone. Each needs a decision or data from HR or IT.

| # | Needed | From | Blocks |
|---|---|---|---|
| 1 | **Identity provider** (for example Microsoft Entra ID) and app registration | IT | Any shared or staging deployment. The dev login refuses to run outside development. |
| 2 | **Trusted source of each employee's company, location and category** (token claims or an HR-system lookup) | IT and HR | Correct scope filtering for real users. The filter is only as good as these attributes. |
| 3 | **Language model endpoint** (URL, model, key) on IT's GPUs | IT | Better answer quality than the 9B laptop model. Re-run both evaluations after switching. |
| 4 | **Secret store** (`.env` versus Key Vault) | IT | Any shared environment |
| 5 | **Hosting environment** for staging (VM or container platform, network, TLS, backups) | IT | Staging deployment |
| 6 | **Company Git remote** (this repository is currently on a public GitHub account) | IT | Storing anything about real policies with the code |
| 7 | **HR contact routes** (general and confidential, per company or location) | HR | Referrals currently say "contact HR" without a named route. The `hr_contacts` table is empty, and contacts must never be invented. |
| 8 | **Approved policies and scope codes** for the chosen business unit, and confirmation of which employee categories each applies to | HR | Replacing the fictional data. Six real policies were received and tested in a separate local database only. |
| 9 | **Sign-off of the golden question set**: HR's 98 questions and expected answers, reviewed against the hand-graded results | HR | Using the set as the acceptance test |
| 10 | **Retention period** for metrics, feedback and audit records | HR, IT, legal | Retention and deletion jobs |
| 11 | Whether **Redis** (caching) or **Langfuse** (LLM tracing) are wanted | IT | Nothing now; both were deliberately deferred |

## 5. Not implemented

| Item | Status |
|---|---|
| Real authentication (SSO) | Not implemented. The plan is in security-and-evaluation.md §1. |
| **Approved FAQ overrides** | Database tables exist (`faqs`, `faq_sources`, with a four-eyes CHECK), but answering does not use them yet and there is no admin screen for them. |
| Scheduling a future version | Publishing requires the effective date to have arrived. |
| OCR for scanned PDFs | Scanned pages are detected and flagged for manual review, not read. |
| Storing the original uploaded file | Only its SHA-256 and the extracted passages are kept. |
| Multilingual answers, personal records, eligibility decisions | Out of scope by design. |
| Dashboards and alerting | Metrics are stored in `query_metrics`, but nothing displays them or raises alerts. |

## 6. Operational risks (as it stands)

| Risk | Effect | Mitigation now |
|---|---|---|
| Anyone who can reach the API can pick any dev user, including an HR administrator | Full access, including publishing | All ports bound to `127.0.0.1`; settings refuse dev login outside development. **Do not expose it on a network.** |
| One machine, one backend process, laptop model | Slow answers (20–60 s), no redundancy; a restart stops Docker and Ollama | Acceptable for demonstrations only |
| Model run-to-run variance | The same question can be answered once and referred the next time | Judge changes on repeated evaluation runs; the validator blocks invented numbers |
| Answers can be wrong without a number in them | A wrong "yes" or "no" passes the number check | Human review of evaluation answers; citations let employees check |
| Real policy text on a developer laptop | Disclosure if the laptop or a backup leaks | Separate database; never in the repository; backups treated as sensitive |
| Public repository | Accidental commit of real data or secrets | `.gitignore` for `.env` and data; after a secret-scanning alert (2026-10-16), no password is in any committed file; real files kept outside the repository |
| `.env` secrets in plain text | Local disclosure | Development only; a secret store is needed (#4) |
| No backups scheduled | Data loss | Manual `pg_dump` procedure in operations.md §7 |
| New vulnerabilities in dependencies | Known CVEs appear over time | Scanned by hand on 2026-11-04: 0 known after upgrades. Versions pinned in `uv.lock` and `package-lock.json`; automatic scanning is in the hardening plan |
| A burst of questions on the laptop model | Some people get "busy, try again" | 4 questions at a time, others queue up to 90 s; the app itself stays responsive (stress-tested) |

## 7. Production-hardening plan

In priority order. Items 1–6 are needed before any real employee uses the system.

1. **Authentication and attributes:**
   - integrate the identity provider: the frontend signs in with MSAL; the backend validates the token's signature, issuer, audience and expiry;
   - map company, location, category and the `hr_admin` role from trusted sources;
   - remove the dev login from production builds;
   - add tests for expired, wrong-audience and missing-claim tokens.
2. **Secrets and configuration:**
   - take every secret from the approved store;
   - rotate the development values;
   - no `.env` files on servers.
3. **Hosting:**
   - deploy the same images to the approved platform with TLS;
   - private networking between the backend, Postgres and Qdrant;
   - managed or backed-up Postgres with point-in-time recovery;
   - Qdrant on persistent storage;
   - the IT-hosted model endpoint.
4. **Real data and contacts:**
   - load the approved policies through the portal;
   - add real scope codes and HR contact routes;
   - re-measure the confidence gate (0.55) on real policies.
5. **Acceptance evaluation:**
   - HR signs off the golden set;
   - run `mypal-eval-answers` on the production model and record the results;
   - agree a pass threshold, with **zero unsafe answers** as a hard requirement.
6. **Security checks:**
   - dependency vulnerability scanning (for example `pip-audit` and `npm audit`) in CI;
   - rate limiting on `/api/chat`;
   - an independent penetration test;
   - a Content-Security-Policy header;
   - malware scanning of uploads.
7. **CI pipeline:** on every change, run the backend tests (with Postgres and Qdrant service containers), the frontend tests, typecheck, lint and the image builds.
8. **Observability:**
   - ship the JSON logs to the central log platform;
   - add dashboards for outcome mix, latency, referral rate and feedback;
   - alerts on readiness failures and model errors.
9. **Operations:** scheduled backups with tested restores; retention jobs once #10 is decided; a runbook owner.
10. **Product gaps, if HR wants them:**
    - FAQ overrides;
    - scheduled future versions;
    - OCR for scanned policies;
    - storing the original files (in approved storage).
11. **Scale, only when measured load requires it:**
    - several backend workers or replicas;
    - an async model client;
    - caching (the deferred Redis question).

## 8. Handover checklist

Before handing over:
- [ ] All phase commits pushed; `git status` clean.
- [ ] A new developer follows [operations.md](operations.md) on their own machine, and the stack, `load-demo`, `pytest` and one chat question work.
- [ ] Real policies, HR's question files and their results are **not** in the repository, and are passed on through an approved channel only.
- [ ] Development secrets are not reused anywhere else.
- [ ] Section 4 has been sent to HR and IT, with owners and dates.
