# My Pal frontend

Employee chat interface for the My Pal HR policy assistant. React 19 + TypeScript + Vite + Tailwind CSS 4.

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

## Behaviour worth knowing

- **Development login stand-in.** The header picker chooses one of the server's fictional test users and sends it as `X-Dev-User`. The browser cannot set a company, location or category. Real SSO replaces this.
- **No server-side transcript.** The conversation exists only in the browser tab. Because the server does not remember earlier questions, a reply to a clarification is sent as "original question (Clarification: reply)".
- **Feedback** sends only the answer id, helpful / not helpful, and an optional reason from a fixed list.
- **States.** Loading (with a note when an answer takes longer than 8 seconds), answer with sources, clarification, referral to HR (with the configured HR contact, if any), and errors with "Try again".
- **Accessibility.** Labelled controls, visible focus, a live region announcing new messages, Enter to send and Shift+Enter for a new line.
