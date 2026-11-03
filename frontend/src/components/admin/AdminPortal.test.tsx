import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import type { PolicySummary, Principal, VersionDetail, VersionStatus } from '../../api/types'
import { AdminPortal } from './AdminPortal'

const principal = (subject: string, roles: string[]): Principal => ({
  subject,
  company_code: 'DEMO-HEALTH',
  location_code: null,
  category_code: null,
  roles,
  is_development_login: true,
})
const USERS = [
  principal('dev-employee-north', []),
  principal('dev-hr-admin', ['hr_admin']),
  principal('dev-hr-reviewer', ['hr_admin']),
]

function version(id: string, label: string, status: VersionStatus): VersionDetail {
  return {
    id,
    version_label: label,
    status,
    effective_from: '2026-01-01',
    source_filename: `leave-${label}.pdf`,
    created_by: 'dev-hr-admin',
    created_at: '2026-11-01T09:00:00Z',
    approved_by: status === 'draft' || status === 'in_review' ? null : 'dev-hr-reviewer',
    published_at: null,
    policy_key: 'leave-policy',
    policy_title: 'Leave Policy',
    policy_owner: 'HR Operations (fictional)',
    source_link: null,
    supersedes_version_id: null,
    scopes: [{ company_code: 'DEMO-HEALTH', location_code: null, category_code: null }],
    parse_report: {
      format: 'pdf',
      page_count: 2,
      chunk_count: 1,
      table_chunk_count: 0,
      issues: [{ severity: 'warning', code: 'no_text_layer', message: 'Page 2 has no text.', page: 2 }],
      needs_manual_review: true,
      blocking: false,
    },
    chunks: [
      {
        ordinal: 0,
        kind: 'text',
        heading_path: ['3. Leave', '3.2 Sick leave'],
        section_ref: '3.2',
        page_start: 1,
        page_end: 1,
        text: 'Employees get 10 days of sick leave per year.',
      },
    ],
    history: [
      {
        occurred_at: '2026-11-01T09:00:00Z',
        actor_id: 'dev-hr-admin',
        action: 'policy_version.upload',
        before: null,
        after: { status: 'draft' },
      },
    ],
  }
}

let versions: Record<string, VersionDetail>
let calls: { url: string; method: string; body: unknown; headers: Record<string, string> }[]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function register(): PolicySummary[] {
  return [
    {
      policy_key: 'leave-policy',
      title: 'Leave Policy',
      owner: 'HR Operations (fictional)',
      versions: Object.values(versions),
    },
  ]
}

const NEXT: Record<string, VersionStatus> = {
  submit: 'in_review',
  approve: 'approved',
  reject: 'rejected',
  publish: 'active',
  restore: 'active',
}

beforeEach(() => {
  calls = []
  localStorage.clear()
  versions = {
    v1: version('v1', 'v1', 'active'),
    v2: version('v2', 'v2', 'in_review'),
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const body =
        init.body instanceof FormData ? init.body : init.body ? JSON.parse(String(init.body)) : undefined
      const headers = (init.headers ?? {}) as Record<string, string>
      calls.push({ url, method: init.method ?? 'GET', body, headers })
      if (url === '/api/dev/users') return json(USERS)
      if (url === '/api/me') return json(USERS.find((u) => u.subject === headers['X-Dev-User']))
      if (url === '/api/admin/policies') return json(register())
      if (url === '/api/admin/reference') {
        return json({
          companies: [{ code: 'DEMO-HEALTH', name: 'Demo Health Services (fictional)' }],
          locations: [{ code: 'DEMO-NORTH', name: 'North Campus (fictional)' }],
          categories: [{ code: 'PERMANENT', name: 'Permanent employee' }],
        })
      }
      if (url === '/api/admin/versions' && init.method === 'POST') {
        versions.v3 = version('v3', 'v3', 'draft')
        return json(versions.v3, 201)
      }
      const match = url.match(/^\/api\/admin\/versions\/([^/]+)(?:\/(\w+))?$/)
      if (match) {
        const [, id, action] = match
        if (action) versions[id] = { ...versions[id], status: NEXT[action] }
        return json(versions[id])
      }
      return json({ error: { code: 'not_found', message: 'Not found' } }, 404)
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

async function openVersion(label: string) {
  const user = userEvent.setup()
  const list = await screen.findByRole('list', { name: 'Policies' })
  await user.click(within(list).getByRole('button', { name: new RegExp(`^${label}`) }))
  await screen.findByRole('article', { name: `Leave Policy ${label}` })
  return user
}

describe('HR admin portal', () => {
  it('is offered to HR administrators only', async () => {
    localStorage.setItem('mypal.devUser', 'dev-employee-north')
    const { unmount } = render(<App />)
    await screen.findByText(/DEMO-HEALTH/)
    expect(screen.queryByRole('button', { name: 'HR admin' })).not.toBeInTheDocument()
    unmount()

    localStorage.setItem('mypal.devUser', 'dev-hr-admin')
    render(<App />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'HR admin' }))
    expect(await screen.findByRole('heading', { name: 'Policy register' })).toBeInTheDocument()
  })

  it('previews the passages, quality issues and history of a version', async () => {
    render(<AdminPortal devUser="dev-hr-reviewer" />)
    await openVersion('v2')

    const detail = screen.getByRole('article', { name: 'Leave Policy v2' })
    expect(detail).toHaveTextContent('Extracted passages (1)')
    expect(detail).toHaveTextContent('3. Leave › 3.2 Sick leave')
    expect(detail).toHaveTextContent('Warning: Page 2 has no text. (page 2)')
    expect(detail).toHaveTextContent('Uploaded by dev-hr-admin')
  })

  it('does not offer approval to the uploader (four-eyes rule)', async () => {
    render(<AdminPortal devUser="dev-hr-admin" />)
    await openVersion('v2')

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    expect(screen.getByText(/another HR administrator must review it/)).toBeInTheDocument()
  })

  it('lets a second administrator approve, then publish after confirming', async () => {
    render(<AdminPortal devUser="dev-hr-reviewer" />)
    const user = await openVersion('v2')

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await user.click(await screen.findByRole('button', { name: 'Publish' }))
    const confirm = screen.getByRole('group', { name: 'Confirm publish' })
    expect(confirm).toHaveTextContent('It replaces v1 for every employee it applies to')
    await user.click(within(confirm).getByRole('button', { name: 'Publish' }))

    await waitFor(() => expect(versions.v2.status).toBe('active'))
    const actions = calls.filter((c) => c.method === 'POST').map((c) => c.url)
    expect(actions).toEqual(['/api/admin/versions/v2/approve', '/api/admin/versions/v2/publish'])
    expect(calls.at(-2)?.headers['X-Dev-User']).toBe('dev-hr-reviewer')
  })

  it('needs a reason before restoring a superseded version', async () => {
    versions.v0 = version('v0', 'v0', 'superseded')
    render(<AdminPortal devUser="dev-hr-admin" />)
    const user = await openVersion('v0')

    await user.click(screen.getByRole('button', { name: 'Restore this version' }))
    const confirm = screen.getByRole('group', { name: 'Confirm restore' })
    const restore = within(confirm).getByRole('button', { name: 'Restore' })
    expect(restore).toBeDisabled()
    await user.type(within(confirm).getByLabelText(/Reason/), 'v1 has the wrong numbers')
    await user.click(restore)

    await waitFor(() => expect(versions.v0.status).toBe('active'))
    const post = calls.find((c) => c.url === '/api/admin/versions/v0/restore')
    expect(post?.body).toEqual({ reason: 'v1 has the wrong numbers' })
  })

  it('checks the upload form before sending, then sends the document as a draft', async () => {
    render(<AdminPortal devUser="dev-hr-admin" />)
    const user = userEvent.setup()
    await screen.findByRole('list', { name: 'Policies' })
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    await user.click(await screen.findByRole('button', { name: 'Upload as draft' }))
    const problems = screen.getByRole('alert')
    expect(problems).toHaveTextContent('Version label')
    expect(problems).toHaveTextContent('Document: choose a PDF or Word (.docx) file.')
    expect(calls.some((c) => c.url === '/api/admin/versions')).toBe(false)

    await user.type(screen.getByLabelText('Version label'), 'v3')
    await user.type(screen.getByLabelText('Effective from'), '2026-12-01')
    await user.selectOptions(screen.getByLabelText('Employee category 1'), 'PERMANENT')
    await user.upload(
      screen.getByLabelText(/Document/),
      new File(['%PDF-1.7'], 'leave-v3.pdf', { type: 'application/pdf' }),
    )
    await user.click(screen.getByRole('button', { name: 'Upload as draft' }))

    await screen.findByRole('article', { name: 'Leave Policy v3' })
    const form = calls.find((c) => c.url === '/api/admin/versions')?.body as FormData
    expect(form.get('policy_key')).toBe('leave-policy')
    expect(form.get('version_label')).toBe('v3')
    expect(form.getAll('scope')).toEqual(['DEMO-HEALTH:*:PERMANENT'])
    expect((form.get('file') as File).name).toBe('leave-v3.pdf')
  })
})
