import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'

import { server } from '../test/setup'
import { ApiError, api } from './api'
import { formatPosition } from './formatPosition'
import { formatExactTime, formatRelativeTime } from './formatTime'
import { lastProgressAt } from './lastProgressAt'
import { assignReaderColour, initialOf, readerColourFor } from './readerColour'
import { MIN_SCALE, spineScale } from './spineScale'
import { readSetting, writeSetting } from './storage'
import { positionProblem } from './positionRules'
import { CLAMP_CHARS, isClampable, needsFetch } from './truncation'

describe('spineScale', () => {
  it('uses total chapters when known', () => {
    expect(spineScale(30, 12)).toEqual({ max: 30, isEstimated: false })
  })

  it('infers with headroom when unknown', () => {
    expect(spineScale(null, 50)).toEqual({ max: 60, isEstimated: true })
  })

  it('rounds the headroom up', () => {
    expect(spineScale(null, 11).max).toBe(14)
  })

  it('has a minimum of ten', () => {
    expect(spineScale(null, 3)).toEqual({ max: MIN_SCALE, isEstimated: true })
  })

  it('returns the minimum with no observations and no total', () => {
    expect(spineScale(null, null)).toEqual({ max: MIN_SCALE, isEstimated: true })
  })

  it('contains a chapter beyond a stated total', () => {
    expect(spineScale(30, 400)).toEqual({ max: 400, isEstimated: false })
  })

  it('keeps a stated total below the minimum as the true scale', () => {
    expect(spineScale(3, null)).toEqual({ max: 3, isEstimated: false })
  })

  // These cases mirror tests/unit/domain/test_services.py exactly. If the two
  // ever disagree, delete this copy and render only what the API sends.
  it.each([
    [30, 12, 30, false],
    [null, 50, 60, true],
    [null, 3, 10, true],
    [null, null, 10, true],
    [30, 400, 400, false],
    [3, null, 3, false],
    [null, 11, 14, true],
  ])('matches the backend for (%s, %s)', (total, observed, max, isEstimated) => {
    expect(spineScale(total, observed)).toEqual({ max, isEstimated })
  })
})

describe('formatPosition', () => {
  it('renders chapter and page', () => {
    expect(formatPosition({ chapter: 12, page: 204 })).toBe('Ch 12 · p.204')
  })

  it('renders chapter alone', () => {
    expect(formatPosition({ chapter: 12, page: null })).toBe('Ch 12')
  })

  it('returns null with no chapter', () => {
    expect(formatPosition(null)).toBeNull()
    expect(formatPosition({ chapter: null })).toBeNull()
  })
})

describe('formatRelativeTime', () => {
  const now = new Date('2026-03-01T12:00:00Z')
  const ago = (seconds) => new Date(now.getTime() - seconds * 1000).toISOString()

  it('renders minutes, hours and days', () => {
    expect(formatRelativeTime(ago(30), now)).toBe('just now')
    expect(formatRelativeTime(ago(180), now)).toBe('3m ago')
    expect(formatRelativeTime(ago(3 * 3600), now)).toBe('3h ago')
    expect(formatRelativeTime(ago(2 * 86400), now)).toBe('2 days ago')
  })

  it('says one day rather than 1 days', () => {
    expect(formatRelativeTime(ago(86400), now)).toBe('1 day ago')
  })

  it('renders nothing for a missing timestamp', () => {
    expect(formatRelativeTime(null, now)).toBe('')
    expect(formatExactTime(null)).toBe('')
  })

  it('formats an exact time for the hover title', () => {
    expect(formatExactTime('2026-03-01T12:00:00Z')).toMatch(/2026/)
  })
})

describe('readerColour', () => {
  it('is stable for a given roster index', () => {
    expect(assignReaderColour(0)).toBe('var(--reader-a)')
    expect(assignReaderColour(1)).toBe('var(--reader-b)')
    expect(assignReaderColour(0)).toBe('var(--reader-a)')
  })

  it('falls back to muted for a member outside the roster', () => {
    expect(readerColourFor('Alan', ['Ada', 'Grace'])).toBe('var(--muted)')
    expect(assignReaderColour(null)).toBe('var(--muted)')
  })

  it('resolves a colour from the roster position', () => {
    expect(readerColourFor('Grace', ['Ada', 'Grace'])).toBe('var(--reader-b)')
  })

  it('wraps rather than crashing beyond the palette', () => {
    expect(assignReaderColour(2)).toBe('var(--reader-a)')
  })

  it('takes an initial from a name', () => {
    expect(initialOf('ada')).toBe('A')
    expect(initialOf('')).toBe('?')
  })
})

describe('api client', () => {
  it('normalises an error body to a message', async () => {
    server.use(
      http.get('/api/books', () =>
        HttpResponse.json({ error: 'A book needs a title.' }, { status: 400 }),
      ),
    )
    await expect(api.books()).rejects.toThrow('A book needs a title.')
  })

  it('surfaces a network failure as a readable message', async () => {
    server.use(http.get('/api/books', () => HttpResponse.error()))
    await expect(api.books()).rejects.toThrow(/Is the backend running/)
  })

  it('falls back to a status message when the body has no error field', async () => {
    server.use(http.get('/api/books', () => new HttpResponse(null, { status: 503 })))
    await expect(api.books()).rejects.toThrow('Something went wrong (503).')
  })

  it('carries the status on the error', async () => {
    server.use(http.get('/api/books', () => HttpResponse.json({ error: 'no' }, { status: 404 })))
    await expect(api.books()).rejects.toMatchObject({ status: 404, name: 'ApiError' })
  })

  it('returns null for 204', async () => {
    server.use(http.delete('/api/posts/p1', () => new HttpResponse(null, { status: 204 })))
    await expect(api.deletePost('p1')).resolves.toBeNull()
  })

  it('sends the feed viewer as a query parameter', async () => {
    let seen
    server.use(
      http.get('/api/books/b1/feed', ({ request }) => {
        seen = new URL(request.url).searchParams.get('as')
        return HttpResponse.json({ posts: [] })
      }),
    )
    await api.feed('b1', { as: 'Grace' })
    expect(seen).toBe('Grace')
  })

  it('omits the viewer when not viewing as someone else', async () => {
    let url
    server.use(
      http.get('/api/books/b1/feed', ({ request }) => {
        url = request.url
        return HttpResponse.json({ posts: [] })
      }),
    )
    await api.feed('b1')
    expect(url).not.toContain('as=')
  })

  it('posts a JSON body', async () => {
    let body
    server.use(
      http.post('/api/posts', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 'p1' }, { status: 201 })
      }),
    )
    await api.createPost({ book_id: 'b1', type: 'Thought', body: 'hi' })
    expect(body).toEqual({ book_id: 'b1', type: 'Thought', body: 'hi' })
  })

  it('is an ApiError subclass so callers can branch on it', () => {
    expect(new ApiError('x', 400)).toBeInstanceOf(Error)
  })
})

describe('lastProgressAt', () => {
  const progress = (member, at) => ({ member, type: 'Progress', created_at: at })

  it('reports the newest progress post per member', () => {
    expect(
      lastProgressAt([
        progress('Ada', '2026-03-01T09:00:00Z'),
        progress('Ada', '2026-03-04T09:00:00Z'),
        progress('Grace', '2026-03-02T09:00:00Z'),
      ]),
    ).toEqual({ Ada: '2026-03-04T09:00:00Z', Grace: '2026-03-02T09:00:00Z' })
  })

  it('keeps the newest whichever order it arrives in', () => {
    expect(
      lastProgressAt([
        progress('Ada', '2026-03-04T09:00:00Z'),
        progress('Ada', '2026-03-01T09:00:00Z'),
      ]),
    ).toEqual({ Ada: '2026-03-04T09:00:00Z' })
  })

  it('ignores thoughts, which are not a claim to have arrived anywhere', () => {
    expect(
      lastProgressAt([
        { member: 'Ada', type: 'Thought', created_at: '2026-03-09T09:00:00Z' },
        progress('Ada', '2026-03-01T09:00:00Z'),
      ]),
    ).toEqual({ Ada: '2026-03-01T09:00:00Z' })
  })

  it('skips a timestamp it cannot read rather than reporting NaN', () => {
    expect(lastProgressAt([progress('Ada', 'not a date')])).toEqual({})
  })

  it('handles no posts at all', () => {
    expect(lastProgressAt()).toEqual({})
  })
})

describe('storage', () => {
  beforeEach(() => window.localStorage.clear())

  it('round-trips a value', () => {
    writeSetting('theme', 'dark')
    expect(readSetting('theme')).toBe('dark')
  })

  it('namespaces its keys so it cannot collide with anything else', () => {
    writeSetting('theme', 'dark')
    expect(window.localStorage.getItem('bookclub.theme')).toBe('"dark"')
  })

  it('returns the fallback for a key that was never written', () => {
    expect(readSetting('theme', 'light')).toBe('light')
  })

  it('returns the fallback rather than throwing on corrupt JSON', () => {
    window.localStorage.setItem('bookclub.panels', '{oh no')
    expect(readSetting('panels', {})).toEqual({})
  })

  it('reports a failed write instead of taking the page down with it', () => {
    const setItem = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new DOMException('QuotaExceededError')
      })
    expect(writeSetting('theme', 'dark')).toBe(false)
    setItem.mockRestore()
  })

  it('survives a browser that throws on read', () => {
    const getItem = vi
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new DOMException('SecurityError')
      })
    expect(readSetting('theme', 'light')).toBe('light')
    getItem.mockRestore()
  })
})

describe('truncation', () => {
  const of = (o) => ({ body_preview: '', has_full_body: false, ...o })

  it('clamps a post whose remainder lives elsewhere', () => {
    expect(isClampable(of({ has_full_body: true, body_preview: 'short' }))).toBe(true)
    expect(needsFetch(of({ has_full_body: true }))).toBe(true)
  })

  it('clamps a merely long post, and opens it without a request', () => {
    const long = of({ body_preview: 'x'.repeat(CLAMP_CHARS + 1) })
    expect(isClampable(long)).toBe(true)
    expect(needsFetch(long)).toBe(false)
  })

  it('leaves a short post alone', () => {
    expect(isClampable(of({ body_preview: 'x'.repeat(CLAMP_CHARS) }))).toBe(false)
  })

  it('handles a post with no body at all', () => {
    expect(isClampable({})).toBe(false)
  })
})

describe('positionProblem', () => {
  const BOOK = { title: 'Piranesi', total_chapters: 45 }
  const at = (chapter, page = '') => positionProblem({ chapter, page }, BOOK)

  it('accepts a chapter inside the book', () => {
    expect(at('44')).toBeNull()
  })

  it('accepts the last chapter', () => {
    expect(at('45')).toBeNull()
  })

  it('rejects one past the end', () => {
    expect(at('46')).toBe('Piranesi has 45 chapters, so there is no chapter 46.')
  })

  // The exact sentence the server sends, so a member sees one wording.
  it('words the rejection the way the backend does', () => {
    expect(at('99')).toBe('Piranesi has 45 chapters, so there is no chapter 99.')
  })

  it('accepts any chapter when the book states no length', () => {
    expect(positionProblem({ chapter: '9000' }, { title: 'X', total_chapters: null }))
      .toBeNull()
  })

  it('accepts any chapter when there is no book yet', () => {
    expect(positionProblem({ chapter: '9000' }, null)).toBeNull()
  })

  it('accepts an empty position', () => {
    expect(at('')).toBeNull()
  })

  // inputMode="numeric" is a keyboard hint, not a constraint: a paste puts
  // anything in the field, and Number('abc') serialises to null.
  it.each(['abc', '1.5', '1e9', '-5', '٤'])(
    'rejects %j as a chapter',
    (raw) => {
      expect(at(raw)).toMatch(/whole number|1 or more/)
    },
  )

  it('treats a whitespace-only chapter as no chapter, not as invalid', () => {
    expect(at('   ')).toBeNull()
  })

  it('rejects zero', () => {
    expect(at('0')).toBe('A chapter is 1 or more.')
  })

  it('tolerates surrounding whitespace', () => {
    expect(at('  12  ')).toBeNull()
  })

  it('rejects a page without a chapter', () => {
    expect(at('', '204')).toBe('A page needs a chapter to go with it.')
  })

  it('rejects a page that is not a whole number', () => {
    expect(at('12', 'xii')).toBe('A page is a whole number.')
  })

  it('accepts a valid chapter and page', () => {
    expect(at('12', '204')).toBeNull()
  })
})
