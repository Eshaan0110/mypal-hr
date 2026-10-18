import type { ChatResponse } from '../api/types'
import { REFERRAL_TITLES } from '../format'
import { Citations } from './Citations'
import { Feedback } from './Feedback'

interface Props {
  response: ChatResponse
  devUser: string
}

/** One reply from My Pal: an answer, a clarification question, or a referral to HR. */
export function AssistantMessage({ response, devUser }: Props) {
  if (response.outcome === 'referral') {
    const contact = response.hr_contact
    return (
      <article
        aria-label="Referral to HR"
        className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3"
      >
        <h3 className="text-sm font-semibold text-amber-900">
          {response.referral_reason ? REFERRAL_TITLES[response.referral_reason] : 'Please contact HR'}
        </h3>
        <p className="mt-1 text-sm text-amber-950">{response.message}</p>
        {contact && (
          <p className="mt-2 text-sm text-amber-950">
            <span className="font-medium">{contact.label}:</span> {contact.route}
            {contact.is_confidential && (
              <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium">
                Confidential
              </span>
            )}
          </p>
        )}
        <Feedback answerId={response.answer_id} devUser={devUser} />
      </article>
    )
  }

  if (response.outcome === 'clarification') {
    return (
      <article
        aria-label="Clarification needed"
        className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3"
      >
        <h3 className="text-sm font-semibold text-sky-900">A little more detail, please</h3>
        <p className="mt-1 text-sm text-sky-950">{response.message}</p>
        <p className="mt-1 text-xs text-sky-800">Reply below and I'll look again.</p>
      </article>
    )
  }

  return (
    <article
      aria-label="Answer"
      className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-xs"
    >
      <p className="text-sm leading-relaxed whitespace-pre-line text-slate-900">
        {response.message}
      </p>
      <Citations citations={response.citations} />
      <p className="mt-3 text-xs text-slate-500">
        This explains the policy. HR confirms individual cases and exceptions.
      </p>
      <Feedback answerId={response.answer_id} devUser={devUser} />
    </article>
  )
}
