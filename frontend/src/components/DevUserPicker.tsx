import type { Principal } from '../api/types'

interface Props {
  users: Principal[]
  value: string | null
  onChange: (subject: string) => void
  me: Principal | null
}

function describe(user: Principal): string {
  const parts = [user.company_code, user.location_code ?? 'any location', user.category_code ?? 'any category']
  return parts.join(' · ')
}

/**
 * DEVELOPMENT LOGIN STAND-IN. Picks one of the fictional test users the server defines.
 * Replaced by the company login (SSO) when IT provides it.
 */
export function DevUserPicker({ users, value, onChange, me }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-800">
        Dev login
      </span>
      <label htmlFor="dev-user" className="sr-only">
        Development test user
      </label>
      <div className="flex flex-col">
        <select
          id="dev-user"
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value)}
          className="rounded-md border border-slate-300 bg-white py-1 pr-7 pl-2 text-sm"
        >
          {value === null && <option value="">Choose a test user…</option>}
          {users.map((user) => (
            <option key={user.subject} value={user.subject}>
              {user.subject}
            </option>
          ))}
        </select>
        {me && <span className="mt-0.5 text-[11px] text-slate-500">{describe(me)}</span>}
      </div>
    </div>
  )
}
