import type { VersionStatus } from '../../api/types'
import { STATUS_LABELS } from './adminFormat'

const STYLES: Record<VersionStatus, string> = {
  draft: 'border-slate-300 bg-white text-slate-700',
  in_review: 'border-sky-200 bg-sky-50 text-sky-900',
  approved: 'border-brand-100 bg-brand-50 text-brand-800',
  active: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  superseded: 'border-slate-200 bg-slate-100 text-slate-600',
  rejected: 'border-red-200 bg-red-50 text-red-900',
}

export function StatusBadge({ status }: { status: VersionStatus }) {
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-[11px] font-semibold ${STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}
