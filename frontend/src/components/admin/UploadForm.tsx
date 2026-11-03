import { useState } from 'react'

import type { PolicySummary, ReferenceData, VersionDetail } from '../../api/types'
import { api, ApiError } from '../../api/client'

interface Props {
  policies: PolicySummary[]
  reference: ReferenceData
  devUser: string
  onUploaded: (version: VersionDetail) => void
  onCancel: () => void
}

interface ScopeRow {
  company: string
  location: string // '' = all locations
  category: string // '' = all categories
}

const NEW_POLICY = '__new__'
const KEY_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/

const input = 'mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm'
const labelStyle = 'block text-sm font-medium text-slate-800'

/** Upload a new policy, or a new version of an existing one. Stored as a DRAFT. */
export function UploadForm({ policies, reference, devUser, onUploaded, onCancel }: Props) {
  const [policyChoice, setPolicyChoice] = useState(policies[0]?.policy_key ?? NEW_POLICY)
  const [key, setKey] = useState('')
  const [title, setTitle] = useState('')
  const [owner, setOwner] = useState('')
  const [label, setLabel] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [sourceLink, setSourceLink] = useState('')
  const [scopes, setScopes] = useState<ScopeRow[]>([
    { company: reference.companies[0]?.code ?? '', location: '', category: '' },
  ])
  const [file, setFile] = useState<File | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const existing = policies.find((p) => p.policy_key === policyChoice) ?? null

  function validate(): string[] {
    const found: string[] = []
    if (!existing) {
      if (!KEY_PATTERN.test(key)) found.push('Policy key: lower-case letters, numbers and hyphens, e.g. leave-policy.')
      if (title.trim().length < 3) found.push('Title: at least 3 characters.')
      if (owner.trim().length < 2) found.push('Owner: who in HR is responsible for this policy.')
    }
    if (!/^[A-Za-z0-9._-]{1,32}$/.test(label)) found.push('Version label: e.g. v2 or 2026.1 (no spaces).')
    if (!effectiveFrom) found.push('Effective from: the date this version takes effect.')
    if (scopes.some((s) => !s.company)) found.push('Applies to: choose a company for every row.')
    if (!file) found.push('Document: choose a PDF or Word (.docx) file.')
    return found
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const found = validate()
    setProblems(found)
    if (found.length > 0 || !file) return

    const form = new FormData()
    form.append('policy_key', existing ? existing.policy_key : key)
    form.append('title', existing ? existing.title : title.trim())
    form.append('owner', existing ? existing.owner : owner.trim())
    form.append('version_label', label)
    form.append('effective_from', effectiveFrom)
    if (sourceLink.trim()) form.append('source_link', sourceLink.trim())
    for (const s of scopes) form.append('scope', `${s.company}:${s.location || '*'}:${s.category || '*'}`)
    form.append('file', file)

    setBusy(true)
    try {
      onUploaded(await api.adminUpload(form, devUser))
    } catch (error) {
      setProblems([error instanceof ApiError ? error.message : 'The upload failed. Please try again.'])
    } finally {
      setBusy(false)
    }
  }

  function updateScope(index: number, change: Partial<ScopeRow>) {
    setScopes((rows) => rows.map((row, i) => (i === index ? { ...row, ...change } : row)))
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Upload a policy version" className="space-y-4 rounded-lg border border-slate-200 bg-white px-4 py-4">
      <div>
        <h2 className="text-lg font-semibold">Upload a policy version</h2>
        <p className="text-sm text-slate-600">
          It is stored as a draft. Employees cannot see it until it is reviewed, approved by a
          second HR administrator, and published.
        </p>
      </div>

      {problems.length > 0 && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
          <p className="font-medium">Please fix the following:</p>
          <ul className="mt-1 list-disc pl-5">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <label htmlFor="up-policy" className={labelStyle}>Policy</label>
        <select id="up-policy" className={input} value={policyChoice} onChange={(e) => setPolicyChoice(e.target.value)}>
          {policies.map((p) => (
            <option key={p.policy_key} value={p.policy_key}>
              {p.title} (new version)
            </option>
          ))}
          <option value={NEW_POLICY}>A new policy…</option>
        </select>
      </div>

      {!existing && (
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="up-key" className={labelStyle}>Policy key</label>
            <input id="up-key" className={input} value={key} onChange={(e) => setKey(e.target.value)} placeholder="leave-policy" />
          </div>
          <div>
            <label htmlFor="up-title" className={labelStyle}>Title</label>
            <input id="up-title" className={input} value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label htmlFor="up-owner" className={labelStyle}>Owner</label>
            <input id="up-owner" className={input} value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="HR Operations" />
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor="up-label" className={labelStyle}>Version label</label>
          <input id="up-label" className={input} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="v2" />
        </div>
        <div>
          <label htmlFor="up-effective" className={labelStyle}>Effective from</label>
          <input id="up-effective" type="date" className={input} value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} />
        </div>
        <div>
          <label htmlFor="up-link" className={labelStyle}>
            Intranet link <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <input id="up-link" type="url" className={input} value={sourceLink} onChange={(e) => setSourceLink(e.target.value)} placeholder="https://" />
        </div>
      </div>

      <fieldset>
        <legend className={labelStyle}>Applies to</legend>
        <div className="mt-1 space-y-2">
          {scopes.map((row, index) => (
            <div key={index} className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
              <select aria-label={`Company ${index + 1}`} className={input} value={row.company} onChange={(e) => updateScope(index, { company: e.target.value })}>
                {reference.companies.map((c) => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </select>
              <select aria-label={`Location ${index + 1}`} className={input} value={row.location} onChange={(e) => updateScope(index, { location: e.target.value })}>
                <option value="">All locations</option>
                {reference.locations.map((l) => (
                  <option key={l.code} value={l.code}>{l.name}</option>
                ))}
              </select>
              <select aria-label={`Employee category ${index + 1}`} className={input} value={row.category} onChange={(e) => updateScope(index, { category: e.target.value })}>
                <option value="">All categories</option>
                {reference.categories.map((c) => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </select>
              <button
                type="button"
                className="mt-1 rounded-md px-2 text-sm text-slate-600 hover:text-red-700 disabled:opacity-40"
                disabled={scopes.length === 1}
                onClick={() => setScopes((rows) => rows.filter((_, i) => i !== index))}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          className="mt-2 text-sm font-medium text-brand-700 hover:underline"
          onClick={() => setScopes((rows) => [...rows, { company: reference.companies[0]?.code ?? '', location: '', category: '' }])}
        >
          Add another group
        </button>
      </fieldset>

      <div>
        <label htmlFor="up-file" className={labelStyle}>Document (PDF or Word .docx, up to 20 MB)</label>
        <input
          id="up-file"
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="mt-1 block text-sm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="rounded-md bg-brand-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
          {busy ? 'Uploading and checking…' : 'Upload as draft'}
        </button>
        <button type="button" disabled={busy} onClick={onCancel} className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50">
          Cancel
        </button>
      </div>
    </form>
  )
}
