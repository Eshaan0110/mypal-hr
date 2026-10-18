import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import { MAX_QUESTION_CHARS } from '../hooks/useChat'

interface Props {
  onSend: (text: string) => void
  busy: boolean
  disabled: boolean
  clarificationQuestion: string | null
  onCancelClarification: () => void
}

/** The question box. Enter sends, Shift+Enter adds a new line. */
export function Composer({
  onSend,
  busy,
  disabled,
  clarificationQuestion,
  onCancelClarification,
}: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const tooLong = text.length > MAX_QUESTION_CHARS
  const canSend = !busy && !disabled && text.trim().length > 0 && !tooLong

  // Put the cursor back in the box when an answer arrives.
  useEffect(() => {
    if (!busy) inputRef.current?.focus()
  }, [busy])

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!canSend) return
    onSend(text)
    setText('')
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="border-t border-slate-200 bg-white">
      <div className="mx-auto max-w-4xl px-4 py-3">
        {clarificationQuestion && (
          <div className="mb-2 flex items-start justify-between gap-3 rounded-md bg-sky-50 px-3 py-1.5 text-xs text-sky-900">
            <span>
              Replying to: <span className="font-medium">{clarificationQuestion}</span>
            </span>
            <button
              type="button"
              onClick={onCancelClarification}
              className="shrink-0 text-sky-800 underline"
            >
              Ask something else
            </button>
          </div>
        )}
        <div className="flex items-end gap-2">
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <textarea
            id="question"
            ref={inputRef}
            rows={2}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            disabled={disabled}
            placeholder={
              disabled ? 'Choose a test user to start' : 'Ask about leave, travel, benefits…'
            }
            aria-invalid={tooLong}
            aria-describedby="question-help"
            className="min-h-[2.75rem] flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-400 disabled:bg-slate-100"
          />
          <button
            type="submit"
            disabled={!canSend}
            className="h-[2.75rem] rounded-md bg-brand-700 px-4 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy ? 'Waiting…' : 'Ask'}
          </button>
        </div>
        <div id="question-help" className="mt-1 flex justify-between text-[11px] text-slate-500">
          <span>Don't include personal details such as health conditions or salary.</span>
          <span className={tooLong ? 'font-medium text-red-700' : undefined}>
            {text.length}/{MAX_QUESTION_CHARS}
          </span>
        </div>
      </div>
    </form>
  )
}
