import { SUGGESTED_QUESTIONS } from '../content'

interface Props {
  onPick: (question: string) => void
  disabled: boolean
}

export function EmptyState({ onPick, disabled }: Props) {
  return (
    <div className="py-10">
      <h2 className="text-lg font-semibold">Ask about an HR policy</h2>
      <p className="mt-1 max-w-prose text-sm text-slate-600">
        Answers come only from published HR policies that apply to you, with the policy section
        they are based on. If the policies don't cover your question, you'll be directed to HR.
      </p>
      <p className="mt-6 text-xs font-medium tracking-wide text-slate-500 uppercase">
        Try asking
      </p>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {SUGGESTED_QUESTIONS.map((question) => (
          <li key={question}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(question)}
              className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-700 hover:border-brand-600 hover:text-brand-700 disabled:opacity-50"
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
