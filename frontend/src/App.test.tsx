import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import type { ChatResponse, Principal } from './api/types'

const USERS: Principal[] = [
  {
    subject: 'dev-employee-north',
    company_code: 'DEMO-HEALTH',
    location_code: 'DEMO-NORTH',
    category_code: 'PERMANENT',
    is_development_login: true,
  },
  {
    subject: 'dev-other-company',
    company_code: 'DEMO-OTHER',
    location_code: null,
    category_code: 'PERMANENT',
    is_development_login: true,
  },
]

const ANSWER: ChatResponse = {
  answer_id: 'a-1',
  outcome: 'answered',
  message: 'Employees are entitled to 10 days of sick leave per calendar year.',
  citations: [
    {
      chunk_id: 'c-1',
      version_id: 'v-1',
      policy_key: 'leave-policy',
      policy_title: 'Leave Policy',
      version_label: 'v1',
      section: '3.2',
      heading_path: ['3. Types of leave', '3.2 Sick leave'],
      page_start: 1,
      page_end: 1,
      effective_from: '2026-01-01',
      source_link: 'https://intranet.example.test/leave',
    },
  ],
  referral_reason: null,
  hr_contact: null,
}

const REFERRAL: ChatResponse = {
  answer_id: 'a-2',
  outcome: 'referral',
  message: 'I cannot confirm this from the approved policy information available.',
  citations: [],
  referral_reason: 'not_in_policy',
  hr_contact: { label: 'HR desk', route: 'hr@example.test', is_confidential: false },
}

const CLARIFICATION: ChatResponse = {
  answer_id: 'a-3',
  outcome: 'clarification',
  message: 'Do you mean casual leave or sick leave?',
  citations: [],
  referral_reason: null,
  hr_contact: null,
}

type Call = { url: string; method: string; body: unknown; headers: Record<string, string> }

let calls: Call[]
let chatReplies: (ChatResponse | { status: number; body: unknown })[]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  calls = []
  chatReplies = []
  localStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const call: Call = {
        url,
        method: init.method ?? 'GET',
        body: init.body ? JSON.parse(String(init.body)) : undefined,
        headers: (init.headers ?? {}) as Record<string, string>,
      }
      calls.push(call)
      if (url === '/api/dev/users') return json(USERS)
      if (url === '/api/me') {
        return json(USERS.find((u) => u.subject === call.headers['X-Dev-User']))
      }
      if (url === '/api/feedback') return json({ status: 'recorded' })
      if (url === '/api/chat') {
        const reply = chatReplies.shift() ?? ANSWER
        return 'status' in reply ? json(reply.body, reply.status) : json(reply)
      }
      return json({ error: { code: 'not_found', message: 'Not found' } }, 404)
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

const chatCalls = () => calls.filter((c) => c.url === '/api/chat')

async function ask(question: string) {
  const user = userEvent.setup()
  const box = await screen.findByLabelText('Your question')
  await waitFor(() => expect(box).toBeEnabled())
  await user.type(box, question)
  await user.keyboard('{Enter}')
  return user
}

describe('My Pal chat', () => {
  it('shows a cited answer and sends the test user as the login', async () => {
    render(<App />)

    await ask('How many sick leave days do I get?')

    const answer = await screen.findByRole('article', { name: 'Answer' })
    expect(answer).toHaveTextContent('10 days of sick leave')
    expect(within(answer).getByRole('link', { name: 'Leave Policy' })).toHaveAttribute(
      'href',
      'https://intranet.example.test/leave',
    )
    expect(answer).toHaveTextContent('Section 3.2 · Page 1 · Effective 1 Jan 2026')
    expect(answer).toHaveTextContent('3. Types of leave › 3.2 Sick leave')
    expect(chatCalls()[0].headers['X-Dev-User']).toBe('dev-employee-north')
    expect(chatCalls()[0].body).toEqual({ message: 'How many sick leave days do I get?' })
  })

  it('shows the scope attributes the server confirmed for the test user', async () => {
    render(<App />)

    expect(await screen.findByText('DEMO-HEALTH · DEMO-NORTH · PERMANENT')).toBeInTheDocument()
  })

  it('shows a referral with the HR contact', async () => {
    chatReplies = [REFERRAL]
    render(<App />)

    await ask('What is the dress code?')

    const referral = await screen.findByRole('article', { name: 'Referral to HR' })
    expect(referral).toHaveTextContent('The approved policies do not cover this')
    expect(referral).toHaveTextContent('HR desk: hr@example.test')
  })

  it('sends a clarification reply together with the original question', async () => {
    chatReplies = [CLARIFICATION, ANSWER]
    render(<App />)

    const user = await ask('How many days of leave do I get?')
    await screen.findByRole('article', { name: 'Clarification needed' })
    expect(screen.getByText(/Replying to:/)).toBeInTheDocument()

    await user.type(screen.getByLabelText('Your question'), 'sick leave{Enter}')

    await screen.findByRole('article', { name: 'Answer' })
    expect(chatCalls()[1].body).toEqual({
      message: 'How many days of leave do I get? (Clarification: sick leave)',
    })
  })

  it('lets the employee leave a clarification and ask something new', async () => {
    chatReplies = [CLARIFICATION, ANSWER]
    render(<App />)

    const user = await ask('How many days of leave do I get?')
    await user.click(await screen.findByRole('button', { name: 'Ask something else' }))
    await user.type(screen.getByLabelText('Your question'), 'Travel claim deadline?{Enter}')

    await screen.findByRole('article', { name: 'Answer' })
    expect(chatCalls()[1].body).toEqual({ message: 'Travel claim deadline?' })
  })

  it('shows server errors and can retry the same question', async () => {
    chatReplies = [
      { status: 503, body: { error: { code: 'unavailable', message: 'Service is down.' } } },
      ANSWER,
    ]
    render(<App />)

    const user = await ask('How many sick leave days do I get?')
    expect(await screen.findByRole('alert')).toHaveTextContent('Service is down.')

    await user.click(screen.getByRole('button', { name: 'Try again' }))

    await screen.findByRole('article', { name: 'Answer' })
    expect(chatCalls()[1].body).toEqual(chatCalls()[0].body)
  })

  it('records helpful feedback with no text', async () => {
    render(<App />)
    const user = await ask('How many sick leave days do I get?')
    const answer = await screen.findByRole('article', { name: 'Answer' })

    await user.click(within(answer).getByRole('button', { name: 'Yes' }))

    expect(await within(answer).findByText('Thank you for your feedback.')).toBeInTheDocument()
    const feedback = calls.find((c) => c.url === '/api/feedback')!
    expect(feedback.body).toEqual({ answer_id: 'a-1', rating: 'helpful', reason_code: null })
  })

  it('records a not-helpful reason chosen from the fixed list', async () => {
    render(<App />)
    const user = await ask('How many sick leave days do I get?')
    const answer = await screen.findByRole('article', { name: 'Answer' })

    await user.click(within(answer).getByRole('button', { name: 'No' }))
    await user.click(within(answer).getByRole('button', { name: 'Outdated' }))

    await within(answer).findByText('Thank you for your feedback.')
    const feedback = calls.find((c) => c.url === '/api/feedback')!
    expect(feedback.body).toEqual({
      answer_id: 'a-1',
      rating: 'not_helpful',
      reason_code: 'outdated',
    })
  })

  it('sends on Enter but not on Shift+Enter, and blocks over-long questions', async () => {
    const user = userEvent.setup()
    render(<App />)
    const box = await screen.findByLabelText('Your question')
    await waitFor(() => expect(box).toBeEnabled())

    await user.type(box, 'line one{Shift>}{Enter}{/Shift}line two')
    expect(chatCalls()).toHaveLength(0)
    expect(box).toHaveValue('line one\nline two')

    await user.clear(box)
    await user.click(box)
    await user.paste('x'.repeat(1001))
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
    expect(box).toHaveAttribute('aria-invalid', 'true')
  })

  it('starts a fresh conversation when the test user changes', async () => {
    render(<App />)
    const user = await ask('How many sick leave days do I get?')
    await screen.findByRole('article', { name: 'Answer' })

    await user.selectOptions(screen.getByLabelText('Development test user'), 'dev-other-company')

    expect(screen.queryByRole('article', { name: 'Answer' })).not.toBeInTheDocument()
    expect(localStorage.getItem('mypal.devUser')).toBe('dev-other-company')
  })

  it('asks a suggested question with one click', async () => {
    const user = userEvent.setup()
    render(<App />)
    const suggestion = await screen.findByRole('button', {
      name: 'How many sick leave days do I get?',
    })
    await waitFor(() => expect(suggestion).toBeEnabled())

    await user.click(suggestion)

    await screen.findByRole('article', { name: 'Answer' })
    expect(chatCalls()[0].body).toEqual({ message: 'How many sick leave days do I get?' })
  })

  it('explains when the backend cannot be reached', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('My Pal is not reachable')
  })
})
