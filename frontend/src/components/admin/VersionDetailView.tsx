import type { ChunkPreview, VersionAction, VersionDetail } from '../../api/types'
import { formatDate } from '../../format'
import {
  actionLabel,
  auditReason,
  describeScope,
  formatTimestamp,
  STATUS_MEANING,
} from './adminFormat'
import { StatusBadge } from './StatusBadge'
import { VersionActions } from './VersionActions'

interface Props {
  version: VersionDetail
  devUser: string
  activeLabel: string | null
  busy: boolean
  error: string | null
  onAction: (action: VersionAction, reason?: string) => void
}

const SEVERITY_LABELS = { info: 'Info', warning: 'Warning', blocking: 'Blocking' } as const
const SEVERITY_STYLES = {
  info: 'text-slate-700',
  warning: 'text-amber-900',
  blocking: 'text-red-800',
} as const

/** Everything HR needs to review a version: metadata, quality report, passages, history. */
export function VersionDetailView({ version, devUser, activeLabel, busy, error, onAction }: Props) {
  const report = version.parse_report
  return (
    <article aria-label={`${version.policy_title} ${version.version_label}`} className="space-y-5">
      <header className="rounded-lg border border-slate-200 bg-white px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold">
            {version.policy_title} · {version.version_label}
          </h2>
          <StatusBadge status={version.status} />
        </div>
        <p className="mt-1 text-sm text-slate-600">{STATUS_MEANING[version.status]}</p>

        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <Fact label="Effective from" value={version.effective_from ? formatDate(version.effective_from) : '—'} />
          <Fact label="File" value={version.source_filename} />
          <Fact label="Uploaded by" value={`${version.created_by}, ${formatTimestamp(version.created_at)}`} />
          <Fact label="Approved by" value={version.approved_by ?? '—'} />
          <Fact label="Published" value={version.published_at ? formatTimestamp(version.published_at) : '—'} />
          <Fact label="Policy owner" value={version.policy_owner} />
        </dl>
        <div className="mt-2 text-sm">
          <span className="text-slate-500">Applies to: </span>
          {version.scopes.map(describeScope).join('; ')}
        </div>

        <div className="mt-4">
          {error && (
            <p role="alert" className="mb-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
              {error}
            </p>
          )}
          <VersionActions
            key={version.id + version.status}
            version={version}
            devUser={devUser}
            activeLabel={activeLabel}
            busy={busy}
            onAction={onAction}
          />
        </div>
      </header>

      {report && (
        <section aria-labelledby="quality-heading" className="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <h3 id="quality-heading" className="text-sm font-semibold">
            Quality check
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            {report.format.toUpperCase()}
            {report.page_count ? ` · ${plural(report.page_count, 'page')}` : ''} ·{' '}
            {plural(report.chunk_count, 'passage')}
            {report.table_chunk_count ? ` (${report.table_chunk_count} from tables)` : ''}
            {report.needs_manual_review ? ' · needs manual review' : ''}
          </p>
          {report.issues.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm">
              {report.issues.map((issue, index) => (
                <li key={index} className={SEVERITY_STYLES[issue.severity]}>
                  <span className="font-medium">{SEVERITY_LABELS[issue.severity]}:</span> {issue.message}
                  {issue.page ? ` (page ${issue.page})` : ''}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section aria-labelledby="passages-heading" className="rounded-lg border border-slate-200 bg-white px-4 py-3">
        <h3 id="passages-heading" className="text-sm font-semibold">
          Extracted passages ({version.chunks.length})
        </h3>
        <p className="mt-1 text-xs text-slate-500">
          This is exactly what My Pal searches and cites. Check headings, tables and numbers
          against the original document before approving.
        </p>
        <ol className="mt-2 divide-y divide-slate-100">
          {version.chunks.map((chunk) => (
            <ChunkItem key={chunk.ordinal} chunk={chunk} />
          ))}
        </ol>
      </section>

      <section aria-labelledby="history-heading" className="rounded-lg border border-slate-200 bg-white px-4 py-3">
        <h3 id="history-heading" className="text-sm font-semibold">
          History
        </h3>
        <ol className="mt-2 space-y-1.5 text-sm">
          {version.history.map((entry, index) => (
            <li key={index}>
              <span className="font-medium">{actionLabel(entry)}</span>
              <span className="text-slate-600">
                {' '}
                by {entry.actor_id} · {formatTimestamp(entry.occurred_at)}
              </span>
              {auditReason(entry) && (
                <span className="block text-slate-700">Reason: {auditReason(entry)}</span>
              )}
            </li>
          ))}
        </ol>
      </section>
    </article>
  )
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-slate-500">{label}:</dt>
      <dd className="text-slate-900">{value}</dd>
    </div>
  )
}

function ChunkItem({ chunk }: { chunk: ChunkPreview }) {
  const where = [
    chunk.section_ref && `Section ${chunk.section_ref}`,
    chunk.page_start &&
      (chunk.page_end && chunk.page_end !== chunk.page_start
        ? `Pages ${chunk.page_start}–${chunk.page_end}`
        : `Page ${chunk.page_start}`),
    chunk.kind === 'table' && 'Table',
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <li className="py-2">
      <details>
        <summary className="cursor-pointer text-sm">
          <span className="font-medium">{chunk.heading_path.join(' › ') || 'No heading'}</span>
          {where && <span className="ml-2 text-xs text-slate-500">{where}</span>}
        </summary>
        <p className="mt-1.5 text-sm whitespace-pre-line text-slate-800">{chunk.text}</p>
      </details>
    </li>
  )
}
