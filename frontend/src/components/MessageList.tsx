import { useEffect, useRef, useState } from 'react'

import type { ChatItem } from '../hooks/useChat'
import { AssistantMessage } from './AssistantMessage'

interface Props {
  items: ChatItem[]
  devUser: string
  onRetry: (question: string) => void
  busy: boolean
}

function Pending() {
  // Local models can be slow; say so instead of leaving the user guessing.
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 8000)
    return () => clearTimeout(timer)
  }, [])
  return (
    <div role="status" className="flex items-center gap-2 px-1 text-sm text-slate-600">
      <span aria-hidden="true" className="size-2 animate-pulse rounded-full bg-brand-600" />
      Searching the approved policies…
      {slow && <span className="text-xs text-slate-500">This can take up to a minute.</span>}
    </div>
  )
}

export function MessageList({ items, devUser, onRetry, busy }: Props) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end', behavior: 'smooth' })
  }, [items])

  return (
    <div role="log" aria-live="polite" aria-label="Conversation" className="space-y-4 py-6">
      {items.map((item) => {
        switch (item.kind) {
          case 'question':
            return (
              <div key={item.id} className="flex justify-end">
                <p className="max-w-[85%] rounded-lg bg-brand-800 px-4 py-2 text-sm whitespace-pre-line text-white">
                  {item.text}
                </p>
              </div>
            )
          case 'pending':
            return <Pending key={item.id} />
          case 'response':
            return <AssistantMessage key={item.id} response={item.response} devUser={devUser} />
          case 'error':
            return (
              <div
                key={item.id}
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
              >
                <p>{item.message}</p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onRetry(item.question)}
                  className="mt-2 rounded-md border border-red-300 bg-white px-2.5 py-1 text-xs font-medium text-red-800 hover:border-red-400 disabled:opacity-50"
                >
                  Try again
                </button>
              </div>
            )
        }
      })}
      <div ref={endRef} />
    </div>
  )
}
