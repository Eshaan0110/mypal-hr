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
  roles: string[] // e.g. ['hr_admin']; the server still checks the role on every admin request
  is_development_login: boolean
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string }
}

// --- HR administration (backend/src/mypal/schemas/admin.py) ---------------------------------

export type VersionStatus =
  | 'draft'
  | 'in_review'
  | 'approved'
  | 'active'
  | 'superseded'
  | 'rejected'

export interface VersionSummary {
  id: string
  version_label: string
  status: VersionStatus
  effective_from: string | null // ISO date
  source_filename: string
  created_by: string
  created_at: string // ISO timestamp
  approved_by: string | null
  published_at: string | null
}

export interface PolicySummary {
  policy_key: string
  title: string
  owner: string
  versions: VersionSummary[] // newest first
}

export interface Scope {
  company_code: string
  location_code: string | null // null = all locations
  category_code: string | null // null = all categories
}

export interface ChunkPreview {
  ordinal: number
  kind: 'text' | 'table'
  heading_path: string[]
  section_ref: string | null
  page_start: number | null
  page_end: number | null
  text: string
}

export interface QualityIssue {
  severity: 'info' | 'warning' | 'blocking'
  code: string
  message: string
  page?: number | null
}

export interface ParseReport {
  format: 'pdf' | 'docx'
  page_count: number | null
  chunk_count: number
  table_chunk_count: number
  issues: QualityIssue[]
  needs_manual_review: boolean
  blocking: boolean
}

export interface AuditEntry {
  occurred_at: string
  actor_id: string
  action: string // e.g. 'policy_version.publish'
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
}

export interface VersionDetail extends VersionSummary {
  policy_key: string
  policy_title: string
  policy_owner: string
  source_link: string | null
  supersedes_version_id: string | null
  scopes: Scope[]
  parse_report: ParseReport | null
  chunks: ChunkPreview[]
  history: AuditEntry[] // oldest first
}

export interface ReferenceCode {
  code: string
  name: string
}

export interface ReferenceData {
  companies: ReferenceCode[]
  locations: ReferenceCode[]
  categories: ReferenceCode[]
}

export type VersionAction = 'submit' | 'approve' | 'reject' | 'publish' | 'restore'
