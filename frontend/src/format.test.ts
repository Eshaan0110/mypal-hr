import { describe, expect, it } from 'vitest'

import type { Citation } from './api/types'
import { citationDetails, formatDate } from './format'

const base: Citation = {
  chunk_id: 'c',
  version_id: 'v',
  policy_key: 'p',
  policy_title: 'Policy',
  version_label: 'v1',
  section: null,
  heading_path: [],
  page_start: null,
  page_end: null,
  effective_from: null,
  source_link: null,
}

describe('citationDetails', () => {
  it('shows only the parts that are known', () => {
    expect(citationDetails({ ...base, section: '4.1' })).toBe('Section 4.1')
    expect(citationDetails(base)).toBe('')
  })

  it('shows a page range when a passage spans pages', () => {
    expect(citationDetails({ ...base, page_start: 2, page_end: 3 })).toBe('Pages 2–3')
    expect(citationDetails({ ...base, page_start: 2, page_end: 2 })).toBe('Page 2')
  })
})

describe('formatDate', () => {
  it('formats calendar dates without shifting the day across time zones', () => {
    expect(formatDate('2026-01-01')).toBe('1 Jan 2026')
    expect(formatDate('2026-12-31')).toBe('31 Dec 2026')
  })
})
