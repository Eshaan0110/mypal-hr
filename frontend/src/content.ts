import type { FeedbackReason } from './api/types'

// Example questions for the FICTIONAL sample policies (leave, travel, salary advance).
export const SUGGESTED_QUESTIONS = [
  'How many sick leave days do I get?',
  'Can I take earned leave during probation?',
  'What documents do I need for a travel claim?',
  'How many instalments can I repay a salary advance in?',
]

// Fixed feedback reasons (the backend accepts only these codes - never free text).
export const FEEDBACK_REASONS: { code: FeedbackReason; label: string }[] = [
  { code: 'incorrect', label: 'Incorrect' },
  { code: 'outdated', label: 'Outdated' },
  { code: 'unclear', label: 'Unclear' },
  { code: 'not_my_situation', label: "Doesn't fit my situation" },
  { code: 'other', label: 'Other' },
]
