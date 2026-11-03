import { useState } from 'react'

import type { VersionAction, VersionDetail } from '../../api/types'

interface Props {
  version: VersionDetail
  devUser: string
  // Label of the policy's current active version, if another one is active.
  activeLabel: string | null
  busy: boolean
  onAction: (action: VersionAction, reason?: string) => void
}

type Pending = 'publish' | 'reject' | 'restore' | null

const primary =
  'rounded-md bg-brand-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50'
const secondary =
  'rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50'

/**
 * The next step(s) allowed for this version. The server enforces every rule again (status,
 * four-eyes, reasons); these controls only avoid offering steps that would be refused.
 */
export function VersionActions({ version, devUser, activeLabel, busy, onAction }: Props) {
  const [pending, setPending] = useState<Pending>(null)
  const [reason, setReason] = useState('')
  const ownUpload = version.created_by === devUser
  const reasonOk = reason.trim().length >= 5

  function confirm(action: VersionAction) {
    onAction(action, action === 'reject' || action === 'restore' ? reason.trim() : undefined)
    setPending(null)
    setReason('')
  }

  if (pending === 'publish') {
    return (
      <ConfirmBox
        text={
          activeLabel
            ? `Publish ${version.version_label}? It replaces ${activeLabel} for every employee it applies to. ${activeLabel} is kept and can be restored.`
            : `Publish ${version.version_label}? Employees it applies to will get answers from it straight away.`
        }
        confirmLabel="Publish"
        onConfirm={() => confirm('publish')}
        onCancel={() => setPending(null)}
        busy={busy}
      />
    )
  }
  if (pending === 'reject' || pending === 'restore') {
    const restoring = pending === 'restore'
    return (
      <ConfirmBox
        text={
          restoring
            ? `Restore ${version.version_label}?${activeLabel ? ` ${activeLabel} will be superseded.` : ''} The reason is recorded in the audit trail.`
            : `Reject ${version.version_label}? The reason is recorded in the audit trail.`
        }
        confirmLabel={restoring ? 'Restore' : 'Reject'}
        onConfirm={() => confirm(pending)}
        onCancel={() => {
          setPending(null)
          setReason('')
        }}
        busy={busy}
        disabled={!reasonOk}
      >
        <label htmlFor="action-reason" className="mt-2 block text-xs font-medium text-slate-700">
          Reason (at least 5 characters)
        </label>
        <textarea
          id="action-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={2}
          maxLength={1000}
          className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
      </ConfirmBox>
    )
  }

  switch (version.status) {
    case 'draft':
      return (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={primary} disabled={busy} onClick={() => onAction('submit')}>
            Submit for review
          </button>
        </div>
      )
    case 'in_review':
      return (
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={primary}
              disabled={busy || ownUpload}
              onClick={() => onAction('approve')}
            >
              Approve
            </button>
            <button
              type="button"
              className={secondary}
              disabled={busy || ownUpload}
              onClick={() => setPending('reject')}
            >
              Reject
            </button>
          </div>
          {ownUpload && (
            <p className="mt-2 text-xs text-slate-600">
              You uploaded this version, so another HR administrator must review it (four-eyes
              rule).
            </p>
          )}
        </div>
      )
    case 'approved':
      return (
        <button type="button" className={primary} disabled={busy} onClick={() => setPending('publish')}>
          Publish
        </button>
      )
    case 'superseded':
      return (
        <button type="button" className={secondary} disabled={busy} onClick={() => setPending('restore')}>
          Restore this version
        </button>
      )
    default:
      return null // active and rejected: no further step
  }
}

interface ConfirmProps {
  text: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
  busy: boolean
  disabled?: boolean
  children?: React.ReactNode
}

function ConfirmBox({ text, confirmLabel, onConfirm, onCancel, busy, disabled, children }: ConfirmProps) {
  return (
    <div role="group" aria-label={`Confirm ${confirmLabel.toLowerCase()}`} className="rounded-md border border-slate-300 bg-slate-50 p-3">
      <p className="text-sm text-slate-800">{text}</p>
      {children}
      <div className="mt-3 flex gap-2">
        <button type="button" className={primary} disabled={busy || disabled} onClick={onConfirm}>
          {confirmLabel}
        </button>
        <button type="button" className={secondary} disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
