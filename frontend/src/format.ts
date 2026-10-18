import type { Citation, ReferralReason } from './api/types'

const DATE_FORMAT = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})

/** "2026-01-01" -> "1 Jan 2026" (dates from the API are calendar dates, not instants). */
export function formatDate(isoDate: string): string {
  return DATE_FORMAT.format(new Date(`${isoDate}T00:00:00Z`))
}

/** "Section 3.2 · Page 1 · Effective 1 Jan 2026" - only the parts that are known. */
export function citationDetails(citation: Citation): string {
  const parts: string[] = []
  if (citation.section) parts.push(`Section ${citation.section}`)
  if (citation.page_start) {
    parts.push(
      citation.page_end && citation.page_end !== citation.page_start
        ? `Pages ${citation.page_start}–${citation.page_end}`
        : `Page ${citation.page_start}`,
    )
  }
  if (citation.effective_from) parts.push(`Effective ${formatDate(citation.effective_from)}`)
  return parts.join(' · ')
}

/** A short explanation shown above a referral, in plain words. */
export const REFERRAL_TITLES: Record<ReferralReason, string> = {
  personal_records: 'Personal records are not available here',
  sensitive_topic: 'Please use the confidential HR route',
  no_applicable_policy: 'No published policy applies to your profile yet',
  insufficient_evidence: 'The approved policies do not cover this',
  not_in_policy: 'The approved policies do not cover this',
  validation_failed: 'I could not verify an answer against the policy text',
  generation_unavailable: 'The answer service is temporarily unavailable',
}
