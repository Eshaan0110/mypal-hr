# My Pal frontend

Employee chat interface and HR administration portal for the My Pal HR policy assistant. React 19 + TypeScript + Vite + Tailwind CSS 4.

## Run (development)

The backend must be running on `http://127.0.0.1:8000` (see [../backend/README.md](../backend/README.md)).

```bash
npm install
npm run dev        # http://localhost:5173 - /api is proxied to the backend
```

## Check

```bash
npm test           # Vitest + Testing Library (API mocked; no backend needed)
npm run typecheck  # TypeScript, strict mode
npm run lint       # oxlint
npm run build      # production build into dist/
```

## Structure

| Path | Responsibility |
|---|---|
| `src/api/types.ts` | TypeScript copies of the backend response shapes (keep in sync with `backend/src/mypal/schemas/`) |
| `src/api/client.ts` | `fetch` wrapper: dev-login header, timeouts, the standard error envelope |
| `src/hooks/useChat.ts` | Conversation state; sends clarification replies together with the original question |
| `src/components/` | Header and dev-login picker, empty state, messages (answer / clarification / referral / error), citations, feedback, question box |
| `src/content.ts`, `src/format.ts` | Suggested questions and feedback reasons; date and citation formatting |
| `src/components/admin/` | HR admin portal: policy register, upload form, version preview (quality report, passages, history) and lifecycle actions |

## Behaviour worth knowing

- **Development login stand-in.** The header picker chooses one of the server's fictional test users and sends it as `X-Dev-User`. The browser cannot set a company, location or category. Real SSO replaces this.
- **No server-side transcript.** The conversation exists only in the browser tab. Because the server does not remember earlier questions, a reply to a clarification is sent as "original question (Clarification: reply)".
- **Feedback** sends only the answer id, helpful / not helpful, and an optional reason from a fixed list.
- **States.** Loading (with a note when an answer takes longer than 8 seconds), answer with sources, clarification, referral to HR (with the configured HR contact, if any), and errors with "Try again".
- **Accessibility.** Labelled controls, visible focus, a live region announcing new messages, Enter to send and Shift+Enter for a new line.

## HR admin portal

Shown as an **HR admin** tab only when the logged-in user has the `hr_admin` role (`dev-hr-admin` or `dev-hr-reviewer` in development). Hiding the tab is convenience only; the server checks the role on every admin request.

- **Policy register:** every policy and version, with its status (draft, in review, approved, active, superseded, rejected).
- **Upload:** a new policy or a new version of an existing one, with effective date, scope groups (company / location / employee category) and the PDF or Word file. It is checked in the browser first, then stored as a draft.
- **Version preview:** what the status means for employees, the quality check, every extracted passage exactly as My Pal searches and cites it, and the audit history.
- **Actions** follow the status: submit → approve or reject → publish → (later) restore. Approve and Reject are disabled for the uploader (four-eyes rule). Publish, reject and restore ask for confirmation, and reject and restore need a reason.
