import type { AuditEntry, Scope, VersionStatus } from '../../api/types'

export const STATUS_LABELS: Record<VersionStatus, string> = {
  draft: 'Draft',
  in_review: 'In review',
  approved: 'Approved',
  active: 'Active',
  superseded: 'Superseded',
  rejected: 'Rejected',
}

/** What each status means for employees, in plain words. */
export const STATUS_MEANING: Record<VersionStatus, string> = {
  draft: 'Not visible to employees. Check the preview, then submit it for review.',
  in_review: 'Not visible to employees. Waiting for another HR administrator to review it.',
  approved: 'Not visible to employees yet. Publish it to make it the version employees get answers from.',
  active: 'Live: employees in scope get answers from this version.',
  superseded: 'Replaced by a newer version. Kept for history; it can be restored if needed.',
  rejected: 'Declined in review. Upload a corrected version instead.',
}

const ACTION_LABELS: Record<string, string> = {
  'policy_version.upload': 'Uploaded',
  'policy_version.submit': 'Submitted for review',
  'policy_version.approve': 'Approved',
  'policy_version.reject': 'Rejected',
  'policy_version.publish': 'Published',
  'policy_version.supersede': 'Superseded',
  'policy_version.restore': 'Restored',
}

export function actionLabel(entry: AuditEntry): string {
  return ACTION_LABELS[entry.action] ?? entry.action
}

export function auditReason(entry: AuditEntry): string | null {
  const reason = entry.after?.reason
  return typeof reason === 'string' ? reason : null
}

const TIMESTAMP_FORMAT = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** "2026-11-02T04:20:17Z" -> "2 Nov 2026, 09:50 am" in the viewer's time zone. */
export function formatTimestamp(iso: string): string {
  return TIMESTAMP_FORMAT.format(new Date(iso))
}

/** "DEMO-HEALTH · all locations · PERMANENT" */
export function describeScope(scope: Scope): string {
  return [
    scope.company_code,
    scope.location_code ?? 'all locations',
    scope.category_code ?? 'all categories',
  ].join(' · ')
}
