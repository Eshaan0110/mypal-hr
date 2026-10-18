import type {
  ApiErrorBody,
  ChatResponse,
  FeedbackRating,
  FeedbackReason,
  Principal,
} from './types'

// Answers from a local model can take a minute on development hardware.
const CHAT_TIMEOUT_MS = 180_000
const DEFAULT_TIMEOUT_MS = 15_000

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId?: string

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

/**
 * DEVELOPMENT LOGIN STAND-IN: the chosen fictional test user is sent as X-Dev-User.
 * With real SSO this header disappears and the browser sends the login session instead.
 */
async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; devUser?: string; timeoutMs?: number } = {},
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS)
  const headers: Record<string, string> = {}
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.devUser) headers['X-Dev-User'] = options.devUser

  let response: Response
  try {
    response = await fetch(path, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    })
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === 'AbortError'
    throw new ApiError(
      0,
      timedOut ? 'timeout' : 'network_error',
      timedOut
        ? 'The request took too long. Please try again.'
        : 'Could not reach My Pal. Check your connection and try again.',
    )
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null
    throw new ApiError(
      response.status,
      body?.error.code ?? 'http_error',
      body?.error.message ?? `Request failed (${response.status}).`,
      body?.error.request_id,
    )
  }
  return (await response.json()) as T
}

export const api = {
  ask(message: string, devUser: string): Promise<ChatResponse> {
    return request('/api/chat', {
      method: 'POST',
      body: { message },
      devUser,
      timeoutMs: CHAT_TIMEOUT_MS,
    })
  },

  sendFeedback(
    answerId: string,
    rating: FeedbackRating,
    reasonCode: FeedbackReason | null,
    devUser: string,
  ): Promise<{ status: 'recorded' }> {
    return request('/api/feedback', {
      method: 'POST',
      body: { answer_id: answerId, rating, reason_code: reasonCode },
      devUser,
    })
  },

  me(devUser: string): Promise<Principal> {
    return request('/api/me', { devUser })
  },

  devUsers(): Promise<Principal[]> {
    return request('/api/dev/users')
  },
}
