import { useEffect, useState } from 'react'

import { api, ApiError } from './api/client'
import type { Principal } from './api/types'
import { Composer } from './components/Composer'
import { EmptyState } from './components/EmptyState'
import { Header } from './components/Header'
import { MessageList } from './components/MessageList'
import { useChat } from './hooks/useChat'

const DEV_USER_KEY = 'mypal.devUser'
const DEFAULT_DEV_USER = 'dev-employee-north'

function storedDevUser(): string | null {
  try {
    return localStorage.getItem(DEV_USER_KEY)
  } catch {
    return null
  }
}

export default function App() {
  const [devUsers, setDevUsers] = useState<Principal[]>([])
  const [devUser, setDevUser] = useState<string | null>(storedDevUser)
  // The server's view of the current test user (kept with the subject it belongs to, so a
  // stale answer for a previous user is never shown).
  const [confirmed, setConfirmed] = useState<Principal | null>(null)
  const me = confirmed?.subject === devUser ? confirmed : null
  const [startupError, setStartupError] = useState<string | null>(null)
  const chat = useChat(devUser)

  useEffect(() => {
    api
      .devUsers()
      .then((users) => {
        setDevUsers(users)
        setDevUser((current) =>
          current && users.some((u) => u.subject === current)
            ? current
            : (users.find((u) => u.subject === DEFAULT_DEV_USER) ?? users[0])?.subject ?? null,
        )
      })
      .catch((error) =>
        setStartupError(
          error instanceof ApiError && error.status === 0
            ? 'My Pal is not reachable. Make sure the backend is running.'
            : 'My Pal could not start. Please try again later.',
        ),
      )
  }, [])

  // Confirm the identity with the server whenever the test user changes.
  useEffect(() => {
    if (!devUser) return
    api.me(devUser).then(setConfirmed).catch(() => setConfirmed(null))
  }, [devUser])

  function changeUser(subject: string) {
    try {
      localStorage.setItem(DEV_USER_KEY, subject)
    } catch {
      // Storage unavailable (private window): the choice simply isn't remembered.
    }
    chat.reset() // different user, different applicable policies: start a fresh conversation
    setDevUser(subject)
  }

  return (
    <div className="flex h-full flex-col">
      <Header devUsers={devUsers} devUser={devUser} onDevUserChange={changeUser} me={me} />

      <div className="border-b border-amber-200 bg-amber-50">
        <p className="mx-auto max-w-4xl px-4 py-1.5 text-xs text-amber-900">
          Prototype using <strong>fictional sample policies</strong>. Not for real HR decisions.
        </p>
      </div>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-4">
          {startupError && (
            <div
              role="alert"
              className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
            >
              {startupError}
            </div>
          )}
          {chat.items.length === 0 ? (
            <EmptyState onPick={chat.send} disabled={!devUser || chat.busy} />
          ) : (
            devUser && (
              <MessageList
                items={chat.items}
                devUser={devUser}
                onRetry={chat.retry}
                busy={chat.busy}
              />
            )
          )}
        </div>
      </main>

      <Composer
        onSend={chat.send}
        busy={chat.busy}
        disabled={!devUser}
        clarificationQuestion={chat.clarifying?.clarificationQuestion ?? null}
        onCancelClarification={chat.cancelClarification}
      />
    </div>
  )
}
