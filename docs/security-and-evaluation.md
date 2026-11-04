# My Pal: security controls and evaluation (Phase 8)

This document lists which security and correctness controls exist, which tests show they work, the results of the evaluations, and what is still **not** covered. It describes a prototype. It is not a security certification, and nothing here has been reviewed by an independent tester.

## 1. Authentication: still a development stand-in

| | Status |
|---|---|
| How users log in today | A **development stand-in**. The browser picks one of six predefined **fictional** users with the `X-Dev-User` header (`backend/src/mypal/auth/dev.py`). This is not authentication: anyone who can reach the API can pick any of these users. |
| What stops it reaching staging or production | Settings refuse to start with `auth_mode = dev` unless the environment is `development` or `test` (`test_dev_login_stand_in_is_refused_outside_development`). The interface shows a "Dev login" badge next to the user picker. |
| What the stand-in already gets right | A caller can only choose *who* they are, never their company, location, category or role. Those come from the server's own user record, exactly as they will with SSO (`test_client_cannot_choose_its_own_company`). |
| Real login | **Not integrated.** No identity provider has been approved for this prototype. |

**What SSO needs** (for IT to decide). With Microsoft Entra ID (Azure AD), the usual pattern is:
1. The React app signs the user in (MSAL) and sends an access token with every request.
2. The backend checks the token's signature (against the tenant's published keys), issuer, audience and expiry. Then it builds the same `Principal` the stand-in builds today.
3. Mapping:
   - `subject` comes from the user's object id.
   - `hr_admin` comes from an Entra group.
   - **company, location and employee category** must come from a trusted source: token claims that IT configures, or an HR-system lookup. This is the main open question. Without trusted values, the scope filter cannot be trusted either.

Only `auth/dev.py` and the `auth_mode` setting change. Every route already receives a `Principal` from one dependency.

## 2. Threats, controls and tests

The scripted test model plays an attacker's best case: it says whatever a successful injection would make a real model say. So the tests below check the controls that **do not depend on the model behaving**: what reaches the prompt, and what reaches the employee.

| Threat | Control | Tests (backend/tests) |
|---|---|---|
| Seeing another company's, location's or category's policies | **Scope gate** in Postgres: search runs only inside versions that are active, in effect and match the user's company, location and category. Each hit is re-checked against Postgres before use. | `db/test_security.py`: `…cannot_bring_other_scopes_into_the_prompt`, `…location_specific_policy_never_reaches_another_location`; `db/test_scope_and_lifecycle.py` (6 tests); `db/test_chat_api.py::test_other_company_gets_no_policies_and_no_model_call` |
| Client claims a different scope or role | Scope and roles come only from the login (`Principal`); extra request fields are ignored. | `test_client_cannot_choose_its_own_company`, `test_admin_api_is_restricted_to_hr_administrators` |
| Prompt injection in the question | The question is wrapped in tags and escaped, and the model is told it is data (rule 2). If the model obeys anyway, it has only in-scope passages to reveal, and its answer must pass the validator. | `…cannot_bring_other_scopes_into_the_prompt`, `test_a_question_cannot_forge_a_passage`, `test_a_model_that_obeys_an_injection_cannot_show_an_invented_figure`; `answering/test_guard_validator_prompts.py::test_question_cannot_close_the_question_tag` |
| Prompt injection inside a policy document | Passage text is escaped, so it cannot close its tag and pose as another passage. Four-eyes review with a full passage preview is the control against harmful *approved* content. | `test_instructions_inside_a_policy_document_stay_inside_its_passage`, `test_document_text_cannot_close_the_passage_tag` |
| Invented numbers, amounts, dates | The validator rejects any number in the answer that is not in a **cited** passage; the employee gets a referral instead. | `test_invented_number_is_never_shown`, `test_number_from_an_uncited_passage_fails_validation`, `test_a_figure_taken_from_the_passage_not_cited_is_rejected` |
| Fake or wrong citations | Citations are built from the database, only for passage labels the server issued. An unknown label makes the answer a referral. | `test_citation_of_a_passage_never_supplied_is_rejected`, `test_grounded_answer_with_citation_built_from_the_database` |
| Outdated policy shown as current | Only ACTIVE versions in effect today are searched. Replacing or restoring a version switches the index and statuses safely. | `test_replaced_text_leaves_the_prompt_and_returns_after_a_restore`, `test_a_version_is_not_used_before_its_effective_date`, `test_draft_content_is_never_used_even_if_it_is_in_the_index` |
| Conflicting evidence | Prompt rule 6: if passages give different rules and don't say which applies, the model must not choose, and the employee is referred. Mixing figures across passages fails the number check. | `test_the_model_is_told_not_to_choose_between_conflicting_rules`, `test_conflicting_passages_with_no_answer_become_a_referral`, `test_a_figure_taken_from_the_passage_not_cited_is_rejected` |
| Unsupported questions | The confidence gate refers to HR without calling the model. A "not in the passages" reply becomes a referral. | `test_weak_evidence_refers_without_calling_the_model`, `test_empty_model_answer_means_not_in_policy` |
| Personal-record and sensitive questions | A keyword guard sends personal-record questions straight to HR. Sensitive topics always get the confidential route. | `test_personal_record_questions_skip_retrieval_and_model`, the `test_sensitive_question_*` tests |
| Unreviewed policy published | Four-eyes rule in code **and** a database CHECK; publishing only from APPROVED. | `test_uploader_cannot_approve_their_own_version`, `test_uploader_cannot_approve_own_version` (DB), `test_full_lifecycle_with_four_eyes_and_drafts_hidden_from_chat` |
| Tampering with the history | Append-only audit table (database trigger blocks UPDATE and DELETE). | `test_audit_events_cannot_be_changed_or_removed` |
| Script in a source link | Upload accepts only `http(s)` links; React escapes all answer text. | `test_invalid_upload_metadata_is_rejected` (the `javascript:` case) |
| Hostile uploaded file | File type is checked by content, not by name; files over 20 MB are refused. | `ingestion/test_file_checks.py`, `test_a_file_that_is_not_a_policy_document_is_rejected` |
| Error messages leak internals | Fixed error envelope; unexpected errors return a generic message. | `test_unexpected_error_hides_internal_details`, `test_validation_error_lists_fields_without_echoing_input` |
| Chat history retained | Metrics and feedback store no question text, answer text or identity. | `test_every_question_records_metrics_without_text_or_identity`, `test_feedback_table_stores_no_text_or_identity` |

To check that these tests can actually fail, two controls were switched off temporarily on 2026-11-03:
- **Scope filter removed:** both scope tests in `test_security.py` failed.
- **Passage escaping removed:** both tag-forging tests failed.

## 3. Evaluation

### 3.1 Answer evaluation: fictional set (in this repository)

`uv run mypal-eval-answers` runs every question through the **whole** pipeline: guard, scope gate, hybrid search, reranker, confidence gate, the configured model, and the validator. It then checks automatically:
- the outcome;
- the cited policy and section;
- required facts;
- forbidden content;
- that no citation is outside the user's scope.

Details are in [backend/eval/README.md](../backend/eval/README.md).

Run on 2026-11-03 with `qwen3.5:9b` on a laptop: 41 questions over the fictional policies, using four of the fictional users.

| Result | Count |
|---|---|
| Pass | 38 |
| Partial | 3 |
| Fail | 0 |
| **Unsafe** (an answer where a referral was expected, forbidden content, or a scope leak) | **0** |
| Right outcome (answered, clarification or referral) | 41 / 41 |
| Right source, for the answers given | 29 / 29 |

All of these passed:
- 4 injection questions;
- 2 cross-company questions;
- 2 questions on replaced figures;
- 3 unsupported questions;
- 2 personal-record questions;
- 1 sensitive question.

The 3 partials were all **correct but bare**: "No", "No, you do not need a medical certificate" and "No, you cannot have two salary advances at the same time". Prompt rule 4 asks for the rule behind the answer, but the 9B model often leaves it out. The citation shows the rule, but the message does not.

### 3.2 HR's own questions (outside this repository)

The first business unit's HR team supplied 6 real policies and 98 questions with expected answers. They are kept **outside this public repository**, in a separate local database and search collection. The answers were graded by hand against HR's expected answers.

| Run | Correct | Partial | Incorrect | Missed (referred although answerable) |
|---|---|---|---|---|
| Baseline (2026-10-28) | 71 | 18 | 2 | 7 |
| After five fixes | 73 | 18 | 2 | 5 |
| Policy title in search, softer boundary rule (2026-10-29) | 81 | 13 | 2 | 2 |

Search put HR's expected text in the top 5 passages for 95 of the 98 questions. Seven of the 13 partials are bare yes/no answers, the same weakness as above.

**Regression check for prompt rule 6 (2026-11-03).** The 98 questions were run again after the conflicting-rules rule was added. 94 were answered (run 3: 95) and 4 referred (run 3: 3):
- one boundary question that was referred before is now answered correctly;
- two questions that were answered correctly before are now referred.

Asked again **with and without rule 6**, both questions were referred either way. So the rule did not cause the change; the local model gives slightly different results between runs. The answers in this run were not re-graded by hand. Any change to the prompt or the model should be judged on repeated runs, not on a single one.

### 3.3 Retrieval

The retrieval evaluation is in [backend/eval/README.md](../backend/eval/README.md). Hybrid search plus the reranker found the right section first (hit@1) for 88% of questions and in the top 5 for 97%, with MRR 0.91. These figures are for the fictional set.

## 4. Known limitations and residual risks

1. **No real authentication** (section 1). Until SSO, the prototype must only run where the API is reachable by its developers.
2. **The scope filter is only as good as the user's attributes.** With SSO, wrong company, location or category data would show the wrong policies. IT must decide where these attributes come from.
3. **Prompt injection cannot be fully prevented.** The controls limit the *damage*: the model sees only in-scope text, and numbers and citations are checked. They do not stop a model from writing a wrong *sentence* that contains no number, such as "Yes, you are eligible" when the passage says the opposite.
4. **The validator checks numbers and citations, not meaning.** A claim without a number is not checked against the passage. Human review of the evaluation answers covers this; nothing at runtime does.
5. **The keyword guard misses paraphrases** of personal-record and sensitive questions. The model and validator are the fallback, so such a question may get a policy answer instead of a direct referral.
6. **Approved content is trusted.** If a harmful instruction is inside a document that two HR administrators approved, the model will see it as policy text. The control is the review preview, not code.
7. **Conflict handling relies on the model.** Rule 6 tells the model not to choose between conflicting rules. A model that ignores it may answer from one of them. The answer is then still grounded and cited, but incomplete.
8. **Short answers.** The 9B model sometimes answers "Yes" or "No" without the rule. A stronger model (IT's GPU hosting) is expected to help, which should be measured with the same evaluation.
9. **Not covered:**
   - rate limiting per user (there is only the overall chat limit, section 6);
   - dependency scanning in a pipeline (it was run by hand on 2026-11-04, section 6);
   - penetration testing;
   - load testing at more than one machine's scale (section 6 covers one machine);
   - checks for anyone who can write to Postgres or Qdrant directly;
   - testing the original upload files for malware.
10. **Small evaluation sets.** 41 fictional and 98 real questions; one question is about 1–2.5 percentage points. The automatic checks do not judge completeness; every answer is in the results file for a human to review.

## 5. How to reproduce

From `backend/`. The Docker services and Ollama must be running for the evaluations.

```bash
uv run pytest
```

```bash
uv run mypal-eval-answers
```

```bash
uv run mypal-eval-retrieval --rerank-model Xenova/ms-marco-MiniLM-L-6-v2
```

For HR's own set, keep the question file and its results **outside the repository**, then run `uv run mypal-eval-answers --questions <path>`. Results are written next to the question file.

## 6. Stress and failure testing (2026-11-04)

Run against a disposable Docker copy with fictional data, through nginx as a browser would, plus floods from inside the Docker network. The scripts are not in the repository (they create and publish test versions). What they did and what they found:

| Area | What was tried | Result |
|---|---|---|
| Hostile chat input | Empty, spaces only, 1,001 characters, wrong types, unknown fields, malformed JSON, form body, 2 MB body; null bytes, control characters, emoji, right-to-left text, homoglyphs, SQL and HTML injection, a fake JSON answer | All refused (422) or answered safely. Injected text was never echoed as an answer, and data was intact afterwards. **Fixed:** a question of only spaces, and a body with extra fields such as `company_code`, are now refused (they used to be ignored). |
| Login abuse | No user, unknown user, 8 KB header, changed case; employee calling admin routes; bad and unknown version ids, path traversal | 401, 403, 404 or 422 every time, no details leaked |
| Uploads | Empty, renamed text or program, cut-off PDF, 21 MB file, a Word file that expands to 300 MB, `.txt`, odd filenames, bad dates, unknown scope codes, `javascript:` links, 5 KB titles, odd policy keys | All refused with a clear code; the 300 MB expansion is stopped before it is unpacked |
| Simultaneous lifecycle actions | 10 submits, 10 approvals, 8 publishes, 6 restores of one version at once; 6 uploads of one new version at once | Exactly one succeeds each time, the rest get 409, and there is always exactly one active version. **Fixed:** simultaneous duplicate uploads used to give 500 errors (now 409). |
| Feedback | 20 ratings of one answer at once | **Fixed:** used to give 500 errors (two inserts racing for one row); now one atomic insert-or-update. Regression test: `test_simultaneous_ratings_of_one_answer_all_succeed`. |
| Load | 2,000 requests, 100 at a time, on readiness, `/api/me` and the admin register; 160 chat requests, 20 at a time | **Fixed: under 100 simultaneous database requests the whole backend froze.** All 15 connections were held while every worker thread waited for one, and the thread that would release a connection could not run. Now sessions close on the event loop, worker threads are capped at the connection pool size (40), and an exhausted pool answers 503 instead of hanging. After the fix: no errors, about 260 requests a second inside Docker. |
| Many simultaneous questions | 60 real questions at once, checking liveness every 2 s | **Fixed:** before, each question held a worker thread for up to 11 minutes, 19 of 171 liveness checks failed, and answers came long after the browser's 180 s limit. Now 4 questions are answered at a time and the rest wait without holding anything. A question that cannot start within 90 s gets "busy, try again". 0 liveness failures. |
| Dependency outages | Qdrant stopped; Postgres stopped; model server unreachable; each brought back | **Fixed:** Qdrant or Postgres down used to give 500 errors; now 503 with "try again". Liveness stays up, and the app recovers by itself when the service returns (no restart). An unreachable model gives a referral to HR. |
| Dependencies | `pip-audit` on the locked backend packages, `npm audit` on the frontend | **Fixed:** 58 known vulnerabilities in pillow, filelock and certifi (indirect dependencies) were removed by upgrading them and fastembed 0.9.0 → 0.9.1. Retrieval results are unchanged (hit@1 88%, MRR 0.91). Now 0 known. |

**Accepted by design:** feedback can be sent by anyone who knows an answer's id. Feedback stores no identity, so ownership cannot be checked; the id is a random UUID only the person who received the answer has seen.

**Capacity.** One backend process on one laptop. The limit is the language model: on this laptop it answers about one question every 10–20 s, so roughly 4–6 questions a minute. Under a burst, some people get "busy, try again". IT's GPU-hosted model, with `MYPAL_CHAT_MAX_CONCURRENT` raised to match its parallelism, is the way to serve more.

**Answer quality after the fixes.** `mypal-eval-answers` on the fictional set: 37 pass, 3 partial, 1 fail, **0 unsafe**; right source 29/29 (`backend/eval/results/answers-20261104-153501.json`). The one failure, `clarify-01`, was referred to HR instead of being asked a clarification question. It passed 3 of 3 re-runs: this is the model's run-to-run variance (section 4, item 8), not a change in behaviour. None of the fixes touch the answer pipeline.
