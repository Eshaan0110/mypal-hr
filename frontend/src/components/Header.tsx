import type { Principal } from '../api/types'
import { DevUserPicker } from './DevUserPicker'

export type View = 'chat' | 'admin'

interface Props {
  devUsers: Principal[]
  devUser: string | null
  onDevUserChange: (subject: string) => void
  me: Principal | null
  // Offered only to HR administrators; the server enforces the role on every admin request.
  showAdmin: boolean
  view: View
  onViewChange: (view: View) => void
}

const VIEWS: { id: View; label: string }[] = [
  { id: 'chat', label: 'Ask My Pal' },
  { id: 'admin', label: 'HR admin' },
]

export function Header({ devUsers, devUser, onDevUserChange, me, showAdmin, view, onViewChange }: Props) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <div
            aria-hidden="true"
            className="flex size-9 items-center justify-center rounded-md bg-brand-800 text-sm font-bold text-white"
          >
            MP
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight">My Pal</h1>
            <p className="text-xs text-slate-500">HR policy assistant · prototype</p>
          </div>
          {showAdmin && (
            <nav aria-label="Sections" className="ml-4 flex gap-1">
              {VIEWS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-current={view === item.id ? 'page' : undefined}
                  onClick={() => onViewChange(item.id)}
                  className={`rounded-md px-2.5 py-1 text-sm font-medium ${
                    view === item.id ? 'bg-brand-50 text-brand-800' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </nav>
          )}
        </div>
        <DevUserPicker users={devUsers} value={devUser} onChange={onDevUserChange} me={me} />
      </div>
    </header>
  )
}
