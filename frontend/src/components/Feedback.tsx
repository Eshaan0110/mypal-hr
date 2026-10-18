import { useState } from 'react'

import { api, ApiError } from '../api/client'
import type { FeedbackRating, FeedbackReason } from '../api/types'
import { FEEDBACK_REASONS } from '../content'

type Status = 'idle' | 'choosing-reason' | 'sending' | 'done' | 'error'

interface Props {
  answerId: string
  devUser: string
}

/** Helpful / not helpful, with an optional fixed reason. Never free text. */
export function Feedback({ answerId, devUser }: Props) {
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)

  async function submit(rating: FeedbackRating, reason: FeedbackReason | null) {
    setStatus('sending')
    setError(null)
    try {
      await api.sendFeedback(answerId, rating, reason, devUser)
      setStatus('done')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send feedback.')
      setStatus('error')
    }
  }

  if (status === 'done') {
    return <p className="mt-3 text-xs text-slate-500">Thank you for your feedback.</p>
  }

  const buttonClass =
    'rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-700 hover:border-slate-400 disabled:opacity-50'

  return (
    <div className="mt-3">
      {status === 'choosing-reason' ? (
        <fieldset>
          <legend className="text-xs text-slate-600">What was wrong? (optional)</legend>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {FEEDBACK_REASONS.map((reason) => (
              <button
                key={reason.code}
                type="button"
                className={buttonClass}
                onClick={() => submit('not_helpful', reason.code)}
              >
                {reason.label}
              </button>
            ))}
            <button
              type="button"
              className={`${buttonClass} border-transparent text-slate-500`}
              onClick={() => submit('not_helpful', null)}
            >
              Skip
            </button>
          </div>
        </fieldset>
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-600">Was this helpful?</span>
          <button
            type="button"
            className={buttonClass}
            disabled={status === 'sending'}
            onClick={() => submit('helpful', null)}
          >
            Yes
          </button>
          <button
            type="button"
            className={buttonClass}
            disabled={status === 'sending'}
            onClick={() => setStatus('choosing-reason')}
          >
            No
          </button>
        </div>
      )}
      <p className="mt-1.5 text-[11px] text-slate-400">
        Feedback is anonymous: your question and your identity are not stored with it.
      </p>
      {error && (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}
