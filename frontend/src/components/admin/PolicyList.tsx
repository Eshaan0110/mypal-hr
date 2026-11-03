import type { PolicySummary } from '../../api/types'
import { formatDate } from '../../format'
import { StatusBadge } from './StatusBadge'

interface Props {
  policies: PolicySummary[]
  selectedVersionId: string | null
  onSelect: (versionId: string) => void
}

/** Every policy and all of its versions, newest first, in every status. */
export function PolicyList({ policies, selectedVersionId, onSelect }: Props) {
  if (policies.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-6 text-sm text-slate-600">
        No policies yet. Upload the first one.
      </p>
    )
  }
  return (
    <ul className="space-y-3" aria-label="Policies">
      {policies.map((policy) => (
        <li key={policy.policy_key} className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-3 py-2">
            <h3 className="text-sm font-semibold">{policy.title}</h3>
            <p className="text-xs text-slate-500">
              {policy.policy_key} · {policy.owner}
            </p>
          </div>
          <ul>
            {policy.versions.map((version) => {
              const selected = version.id === selectedVersionId
              return (
                <li key={version.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(version.id)}
                    aria-current={selected ? 'true' : undefined}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                      selected ? 'bg-brand-50' : ''
                    }`}
                  >
                    <span>
                      <span className="font-medium">{version.version_label}</span>
                      {version.effective_from && (
                        <span className="ml-2 text-xs text-slate-500">
                          from {formatDate(version.effective_from)}
                        </span>
                      )}
                    </span>
                    <StatusBadge status={version.status} />
                  </button>
                </li>
              )
            })}
          </ul>
        </li>
      ))}
    </ul>
  )
}
