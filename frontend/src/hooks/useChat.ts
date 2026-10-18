import { useCallback, useReducer, useRef } from 'react'

import { api, ApiError } from '../api/client'
import type { ChatResponse } from '../api/types'

/**
 * The conversation lives only in this browser tab. The server stores no transcript (privacy
 * decision): each question is sent on its own.
 *
 * Clarification: when My Pal asks "Do you mean casual or sick leave?", the server does not
 * remember the original question. So the reply is sent together with it, e.g.
 * "How many days of leave do I get? (Clarification: sick leave)".
 */

export const MAX_QUESTION_CHARS = 1000

export type ChatItem =
  | { id: string; kind: 'question'; text: string }
  | { id: string; kind: 'pending' }
  | { id: string; kind: 'response'; question: string; response: ChatResponse }
  | { id: string; kind: 'error'; question: string; message: string }

interface Clarifying {
  originalQuestion: string
  clarificationQuestion: string
}

interface State {
  items: ChatItem[]
  busy: boolean
  clarifying: Clarifying | null
}

type Action =
  | { type: 'sent'; text: string; ids: [string, string] }
  | { type: 'answered'; pendingId: string; question: string; response: ChatResponse }
  | { type: 'failed'; pendingId: string; question: string; message: string }
  | { type: 'cancelClarification' }
  | { type: 'reset' }

const initialState: State = { items: [], busy: false, clarifying: null }

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'sent':
      return {
        ...state,
        busy: true,
        items: [
          ...state.items,
          { id: action.ids[0], kind: 'question', text: action.text },
          { id: action.ids[1], kind: 'pending' },
        ],
      }
    case 'answered': {
      const { response } = action
      return {
        busy: false,
        clarifying:
          response.outcome === 'clarification'
            ? { originalQuestion: action.question, clarificationQuestion: response.message }
            : null,
        items: state.items.map((item) =>
          item.id === action.pendingId
            ? { id: item.id, kind: 'response', question: action.question, response }
            : item,
        ),
      }
    }
    case 'failed':
      return {
        ...state,
        busy: false,
        items: state.items.map((item) =>
          item.id === action.pendingId
            ? { id: item.id, kind: 'error', question: action.question, message: action.message }
            : item,
        ),
      }
    case 'cancelClarification':
      return { ...state, clarifying: null }
    case 'reset':
      return initialState
  }
}

export function composeQuestion(text: string, clarifying: Clarifying | null): string {
  return clarifying ? `${clarifying.originalQuestion} (Clarification: ${text})` : text
}

export function useChat(devUser: string | null) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const counter = useRef(0)
  const nextId = () => `item-${++counter.current}`

  /** Send `question` to the server, showing `display` as what the employee typed. */
  const ask = useCallback(
    async (question: string, display: string) => {
      if (!devUser || state.busy) return
      const pendingId = nextId()
      dispatch({ type: 'sent', text: display, ids: [nextId(), pendingId] })
      try {
        const response = await api.ask(question, devUser)
        dispatch({ type: 'answered', pendingId, question, response })
      } catch (error) {
        const message =
          error instanceof ApiError ? error.message : 'Something went wrong. Please try again.'
        dispatch({ type: 'failed', pendingId, question, message })
      }
    },
    [devUser, state.busy],
  )

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return Promise.resolve()
      return ask(composeQuestion(trimmed, state.clarifying), trimmed)
    },
    [ask, state.clarifying],
  )

  /** Re-send a question exactly as it was sent before (after an error). */
  const retry = useCallback((question: string) => ask(question, question), [ask])

  return {
    items: state.items,
    busy: state.busy,
    clarifying: state.clarifying,
    send,
    retry,
    cancelClarification: () => dispatch({ type: 'cancelClarification' }),
    reset: () => dispatch({ type: 'reset' }),
  }
}
