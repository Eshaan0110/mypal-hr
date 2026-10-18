// Mirrors the backend contracts in backend/src/mypal/schemas/. Keep the two in sync.

export type AnswerOutcome = 'answered' | 'faq' | 'clarification' | 'referral'

export type ReferralReason =
  | 'personal_records'
  | 'sensitive_topic'
  | 'no_applicable_policy'
  | 'insufficient_evidence'
  | 'not_in_policy'
  | 'validation_failed'
  | 'generation_unavailable'

export interface Citation {
  chunk_id: string
  version_id: string
  policy_key: string
  policy_title: string
  version_label: string
  section: string | null
  heading_path: string[]
  page_start: number | null
  page_end: number | null
  effective_from: string | null // ISO date
  source_link: string | null
}

export interface HrContact {
  label: string
  route: string
  is_confidential: boolean
}

export interface ChatResponse {
  answer_id: string
  outcome: AnswerOutcome
  message: string
  citations: Citation[]
  referral_reason: ReferralReason | null
  hr_contact: HrContact | null
}

export type FeedbackRating = 'helpful' | 'not_helpful'
export type FeedbackReason = 'incorrect' | 'outdated' | 'unclear' | 'not_my_situation' | 'other'

export interface Principal {
  subject: string
  company_code: string
  location_code: string | null
  category_code: string | null
  is_development_login: boolean
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string }
}
