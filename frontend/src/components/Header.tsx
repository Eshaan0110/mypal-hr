import type { Principal } from '../api/types'
import { DevUserPicker } from './DevUserPicker'

interface Props {
  devUsers: Principal[]
  devUser: string | null
  onDevUserChange: (subject: string) => void
  me: Principal | null
}

export function Header({ devUsers, devUser, onDevUserChange, me }: Props) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
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
        </div>
        <DevUserPicker users={devUsers} value={devUser} onChange={onDevUserChange} me={me} />
      </div>
    </header>
  )
}
