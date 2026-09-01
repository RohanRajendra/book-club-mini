import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { server } from '../test/setup'
import { useBooks } from './useBooks'
import { useComposer } from './useComposer'
import { useFeed } from './useFeed'
import { useMe } from './useMe'
import { usePanels } from './usePanels'
import { usePostEditor } from './usePostEditor'
import { useReveal } from './useReveal'
import { useTheme } from './useTheme'
import { useToggleSet } from './useToggleSet'

const post = (overrides = {}) => ({
  id: 'p1',
  member: 'Ada',
  type: 'Thought',
  body_preview: 'A thought.',
  has_full_body: false,
  position: { chapter: 9, page: 204 },
  parent_post_id: null,
  created_at: '2026-03-01T12:00:00Z',
  edited_at: '2026-03-01T12:00:00Z',
  was_edited: false,
  is_spoiler: false,
  is_own: true,
  replies: [],
  ...overrides,
})

const feedBody = (posts = [post()]) => ({
  book: { id: 'b1', title: 'Piranesi', author: null, status: 'Currently Reading', total_chapters: 30 },
  posts,
  positions: [
    { member: 'Ada', position: { chapter: 9, page: 204 } },
    { member: 'Grace', position: null },
  ],
  spine: { max_chapter: 30, is_estimated: false },
  counts: { all: posts.length, progress: 0, thought: posts.length, question: 0 },
})

function feedRoute(handler) {
  server.use(http.get('/api/books/:id/feed', handler))
}

describe('useFeed', () => {
  it('loads on mount', async () => {
    feedRoute(() => HttpResponse.json(feedBody()))
    const { result } = renderHook(() => useFeed('b1'))
    await waitFor(() => expect(result.current.posts).toHaveLength(1))
    expect(result.current.book.title).toBe('Piranesi')
  })

  it('exposes an error without clearing existing posts', async () => {
    let calls = 0
    feedRoute(() => {
      calls += 1
      return calls === 1
        ? HttpResponse.json(feedBody())
        : HttpResponse.json({ error: "Can't reach Notion right now." }, { status: 502 })
    })

    const { result } = renderHook(() => useFeed('b1'))
    await waitFor(() => expect(result.current.posts).toHaveLength(1))

    await act(async () => {
      await result.current.refresh()
    })

    expect(result.current.error).toMatch(/Can't reach Notion/)
    expect(result.current.posts).toHaveLength(1)
  })

  it('refreshes on window focus', async () => {
    let calls = 0
    feedRoute(() => {
      calls += 1
      return HttpResponse.json(feedBody())
    })

    renderHook(() => useFeed('b1'))
    await waitFor(() => expect(calls).toBe(1))

    await act(async () => {
      window.dispatchEvent(new Event('focus'))
    })
    await waitFor(() => expect(calls).toBe(2))
  })

  it('does not refresh on focus while a request is in flight', async () => {
    let calls = 0
    let release
    const gate = new Promise((resolve) => {
      release = resolve
    })

    feedRoute(async () => {
      calls += 1
      if (calls === 1) await gate
      return HttpResponse.json(feedBody())
    })

    renderHook(() => useFeed('b1'))
    await waitFor(() => expect(calls).toBe(1))

    // Ten focus events while the first request is still open.
    await act(async () => {
      for (let i = 0; i < 10; i += 1) window.dispatchEvent(new Event('focus'))
    })
    expect(calls).toBe(1)

    await act(async () => {
      release()
      await gate
    })
  })

  it('refetches when the book changes', async () => {
    const seen = []
    feedRoute(({ params }) => {
      seen.push(params.id)
      return HttpResponse.json(feedBody())
    })

    const { rerender } = renderHook(({ id }) => useFeed(id), {
      initialProps: { id: 'b1' },
    })
    await waitFor(() => expect(seen).toEqual(['b1']))

    rerender({ id: 'b2' })
    await waitFor(() => expect(seen).toEqual(['b1', 'b2']))
  })

  it('does not refetch when the filter changes', async () => {
    // Filtering is client-side, so a chip click must cost zero requests and
    // must not lose the counts of the filtered-out types.
    let calls = 0
    feedRoute(() => {
      calls += 1
      return HttpResponse.json(
        feedBody([post({ id: 'a', type: 'Thought' }), post({ id: 'b', type: 'Question' })]),
      )
    })

    const { result } = renderHook(() => useFeed('b1'))
    await waitFor(() => expect(result.current.posts).toHaveLength(2))

    act(() => result.current.setFilter('question'))

    expect(calls).toBe(1)
    expect(result.current.posts.map((p) => p.id)).toEqual(['b'])
    expect(result.current.counts.all).toBe(2)
  })

  it('refetches when the viewer changes', async () => {
    const seen = []
    feedRoute(({ request }) => {
      seen.push(new URL(request.url).searchParams.get('as'))
      return HttpResponse.json(feedBody())
    })

    const { rerender } = renderHook(({ as }) => useFeed('b1', { as }), {
      initialProps: { as: 'Ada' },
    })
    await waitFor(() => expect(seen).toEqual(['Ada']))

    rerender({ as: 'Grace' })
    await waitFor(() => expect(seen).toEqual(['Ada', 'Grace']))
  })

  it('does nothing without a book', async () => {
    const { result } = renderHook(() => useFeed(null))
    expect(result.current.posts).toEqual([])
    expect(result.current.counts.all).toBe(0)
  })

  it('inserts and removes a post optimistically', async () => {
    feedRoute(() => HttpResponse.json(feedBody()))
    const { result } = renderHook(() => useFeed('b1'))
    await waitFor(() => expect(result.current.posts).toHaveLength(1))

    act(() => result.current.insertPost(post({ id: 'new' })))
    expect(result.current.posts[0].id).toBe('new')

    act(() => result.current.removePost('new'))
    expect(result.current.posts.map((p) => p.id)).toEqual(['p1'])
  })
})

describe('useBooks', () => {
  const books = [
    { id: 'b1', title: 'Piranesi', status: 'Currently Reading', author: null, total_chapters: 30 },
    { id: 'b2', title: 'Jonathan Strange', status: 'Upcoming', author: null, total_chapters: null },
  ]

  it('selects the currently reading book by default', async () => {
    server.use(http.get('/api/books', () => HttpResponse.json(books)))
    const { result } = renderHook(() => useBooks())
    await waitFor(() => expect(result.current.selectedId).toBe('b1'))
    expect(result.current.book.title).toBe('Piranesi')
  })

  it('falls back to the first book when none is current', async () => {
    server.use(
      http.get('/api/books', () =>
        HttpResponse.json([{ ...books[1] }, { ...books[0], status: 'Paused' }]),
      ),
    )
    const { result } = renderHook(() => useBooks())
    await waitFor(() => expect(result.current.selectedId).toBe('b2'))
  })

  it('setting a book current refetches the list', async () => {
    let calls = 0
    server.use(
      http.get('/api/books', () => {
        calls += 1
        return HttpResponse.json(
          calls === 1
            ? books
            : [
                { ...books[0], status: 'Paused' },
                { ...books[1], status: 'Currently Reading' },
              ],
        )
      }),
      http.patch('/api/books/b2', () =>
        HttpResponse.json({ ...books[1], status: 'Currently Reading' }),
      ),
    )

    const { result } = renderHook(() => useBooks())
    await waitFor(() => expect(result.current.books).toHaveLength(2))

    await act(async () => {
      await result.current.updateBook('b2', { title: 'Jonathan Strange', status: 'Currently Reading' })
    })

    expect(calls).toBe(2)
    expect(result.current.books.find((b) => b.id === 'b1').status).toBe('Paused')
  })

  it('selects a newly added book', async () => {
    const added = { id: 'b3', title: 'Wolf Hall', status: 'Upcoming', author: null, total_chapters: null }
    let calls = 0
    server.use(
      http.get('/api/books', () => {
        calls += 1
        return HttpResponse.json(calls === 1 ? books : [...books, added])
      }),
      http.post('/api/books', () => HttpResponse.json(added, { status: 201 })),
    )

    const { result } = renderHook(() => useBooks())
    await waitFor(() => expect(result.current.books).toHaveLength(2))

    await act(async () => {
      await result.current.addBook({ title: 'Wolf Hall' })
    })
    expect(result.current.selectedId).toBe('b3')
  })

  it('exposes an error when the list cannot load', async () => {
    server.use(
      http.get('/api/books', () => HttpResponse.json({ error: 'nope' }, { status: 502 })),
    )
    const { result } = renderHook(() => useBooks())
    await waitFor(() => expect(result.current.error).toBe('nope'))
    expect(result.current.books).toEqual([])
  })

  it('handles an empty library', async () => {
    server.use(http.get('/api/books', () => HttpResponse.json([])))
    const { result } = renderHook(() => useBooks())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.selectedId).toBeNull()
    expect(result.current.book).toBeNull()
  })
})

describe('useComposer', () => {
  const position = { chapter: 12, page: 301 }

  it('prefills chapter and page from the viewer position', () => {
    const { result } = renderHook(() => useComposer({ viewerPosition: position }))
    act(() => result.current.chooseType('Thought'))
    expect(result.current.fields.chapter).toBe('12')
    expect(result.current.fields.page).toBe('301')
  })

  it('does not prefill for progress, which states where you are', () => {
    const { result } = renderHook(() => useComposer({ viewerPosition: position }))
    act(() => result.current.chooseType('Progress'))
    expect(result.current.fields.chapter).toBe('')
  })

  it('allows clearing a prefilled chapter', () => {
    const { result } = renderHook(() => useComposer({ viewerPosition: position }))
    act(() => result.current.chooseType('Thought'))
    act(() => result.current.setField('chapter', ''))
    act(() => result.current.setField('body', 'No position on purpose.'))
    expect(result.current.fields.chapter).toBe('')
    expect(result.current.isValid).toBe(true)
  })

  it('clearing the chapter clears the prefilled page with it', () => {
    // Otherwise clearing the chapter leaves a page behind and the post is
    // rejected for a state the member never chose.
    const { result } = renderHook(() => useComposer({ viewerPosition: position }))
    act(() => result.current.chooseType('Thought'))
    expect(result.current.fields.page).toBe('301')

    act(() => result.current.setField('chapter', ''))
    expect(result.current.fields.page).toBe('')
  })

  it('requires a chapter for progress', async () => {
    const { result } = renderHook(() => useComposer({ onSubmit: vi.fn() }))
    act(() => result.current.chooseType('Progress'))
    await act(async () => {
      await result.current.submit()
    })
    expect(result.current.error).toBe('Progress needs a chapter number.')
  })

  it('allows an empty body for progress', async () => {
    const onSubmit = vi.fn().mockResolvedValue({ id: 'p1' })
    const { result } = renderHook(() => useComposer({ onSubmit }))
    act(() => result.current.chooseType('Progress'))
    act(() => result.current.setField('chapter', '4'))
    await act(async () => {
      await result.current.submit()
    })
    expect(onSubmit).toHaveBeenCalledWith({ type: 'Progress', body: '', chapter: 4, page: null })
  })

  it.each(['Thought', 'Question'])('requires a body for %s', async (type) => {
    const { result } = renderHook(() => useComposer({ onSubmit: vi.fn() }))
    act(() => result.current.chooseType(type))
    await act(async () => {
      await result.current.submit()
    })
    expect(result.current.error).toBe('Write something first.')
  })

  it('rejects a page without a chapter', async () => {
    const { result } = renderHook(() => useComposer({ onSubmit: vi.fn() }))
    act(() => result.current.chooseType('Thought'))
    act(() => result.current.setField('body', 'x'))
    act(() => result.current.setField('page', '204'))
    await act(async () => {
      await result.current.submit()
    })
    expect(result.current.error).toBe('A page needs a chapter to go with it.')
  })

  it('keeps its contents when a submit fails', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('Couldn’t save that.'))
    const { result } = renderHook(() => useComposer({ onSubmit }))
    act(() => result.current.chooseType('Thought'))
    act(() => result.current.setField('body', 'Something I do not want to lose.'))

    await act(async () => {
      await result.current.submit()
    })

    expect(result.current.fields.body).toBe('Something I do not want to lose.')
    expect(result.current.error).toMatch(/save/)
  })

  it('clears its contents after a successful submit', async () => {
    const onSubmit = vi.fn().mockResolvedValue({ id: 'p1' })
    const { result } = renderHook(() => useComposer({ onSubmit }))
    act(() => result.current.chooseType('Thought'))
    act(() => result.current.setField('body', 'Posted.'))
    await act(async () => {
      await result.current.submit()
    })
    expect(result.current.fields.body).toBe('')
    expect(result.current.open).toBe(false)
  })

  it('keeps contents across a cancel within the session', () => {
    const { result } = renderHook(() => useComposer({}))
    act(() => result.current.setField('body', 'Half written.'))
    act(() => result.current.cancel())
    expect(result.current.open).toBe(false)
    expect(result.current.fields.body).toBe('Half written.')
  })

  it('shows a character count only past 1,700', () => {
    const { result } = renderHook(() => useComposer({}))
    act(() => result.current.setField('body', 'x'.repeat(1700)))
    expect(result.current.characterCount).toBeNull()

    act(() => result.current.setField('body', 'x'.repeat(1743)))
    expect(result.current.characterCount).toBe(1743)
    expect(result.current.willCollapse).toBe(false)

    act(() => result.current.setField('body', 'x'.repeat(1901)))
    expect(result.current.willCollapse).toBe(true)
  })
})

describe('useReveal', () => {
  it('reveals one post without revealing others', () => {
    const { result } = renderHook(() => useReveal())
    act(() => result.current.reveal('p1'))
    expect(result.current.isRevealed('p1')).toBe(true)
    expect(result.current.isRevealed('p2')).toBe(false)
  })

  it('state does not persist across a remount', () => {
    const first = renderHook(() => useReveal())
    act(() => first.result.current.reveal('p1'))
    first.unmount()

    const second = renderHook(() => useReveal())
    expect(second.result.current.isRevealed('p1')).toBe(false)
  })

  it('expands a post by fetching its full body', async () => {
    server.use(http.get('/api/posts/p1/body', () => HttpResponse.json({ body: 'The whole thing.' })))
    const { result } = renderHook(() => useReveal())

    expect(result.current.bodyFor({ id: 'p1', body_preview: 'The whole…' })).toBe('The whole…')

    await act(async () => {
      await result.current.expand({ id: 'p1', has_full_body: true })
    })

    expect(result.current.isExpanded('p1')).toBe(true)
    expect(result.current.bodyFor({ id: 'p1', body_preview: 'The whole…' })).toBe('The whole thing.')
  })

  // A merely long post is already on the page; opening it must cost nothing.
  it('expands a post that is not stored elsewhere without a request', async () => {
    const { result } = renderHook(() => useReveal())
    const long = { id: 'p1', has_full_body: false, body_preview: 'x'.repeat(900) }

    await act(async () => {
      await result.current.expand(long)
    })

    expect(result.current.isExpanded('p1')).toBe(true)
    expect(result.current.bodyFor(long)).toBe(long.body_preview)
  })

  // The server withholds a body ahead of the viewer unless told otherwise, so
  // the decision has to travel with the request or Read anyway then Read more
  // fails on exactly the posts the feature exists for.
  it('asks for a revealed spoiler with reveal=true', async () => {
    const seen = []
    server.use(
      http.get('/api/posts/p1/body', ({ request }) => {
        seen.push(new URL(request.url).searchParams.get('reveal'))
        return HttpResponse.json({ body: 'The whole thing.' })
      }),
    )
    const { result } = renderHook(() => useReveal())
    const spoiler = { id: 'p1', has_full_body: true, is_spoiler: true }

    act(() => result.current.reveal('p1'))
    await act(async () => {
      await result.current.expand(spoiler)
    })

    expect(seen).toEqual(['true'])
  })

  it('does not ask to reveal a post that is not a spoiler', async () => {
    const seen = []
    server.use(
      http.get('/api/posts/p1/body', ({ request }) => {
        seen.push(new URL(request.url).searchParams.get('reveal'))
        return HttpResponse.json({ body: 'The whole thing.' })
      }),
    )
    const { result } = renderHook(() => useReveal())

    await act(async () => {
      await result.current.expand({ id: 'p1', has_full_body: true, is_spoiler: false })
    })

    expect(seen).toEqual([null])
  })

  it('does not ask to reveal a spoiler the member has not revealed', async () => {
    const seen = []
    server.use(
      http.get('/api/posts/p1/body', ({ request }) => {
        seen.push(new URL(request.url).searchParams.get('reveal'))
        return HttpResponse.json({ body: 'The whole thing.' })
      }),
    )
    const { result } = renderHook(() => useReveal())

    await act(async () => {
      await result.current.expand({ id: 'p1', has_full_body: true, is_spoiler: true })
    })

    expect(seen).toEqual([null])
  })

  it('collapses back to the preview', async () => {
    server.use(http.get('/api/posts/p1/body', () => HttpResponse.json({ body: 'The whole thing.' })))
    const { result } = renderHook(() => useReveal())

    await act(async () => {
      await result.current.expand({ id: 'p1', has_full_body: true })
    })
    act(() => result.current.collapse('p1'))

    expect(result.current.isExpanded('p1')).toBe(false)
    expect(result.current.bodyFor({ id: 'p1', body_preview: 'The whole…' })).toBe('The whole…')
  })

  it('collapsing one post leaves another expanded', async () => {
    server.use(
      http.get('/api/posts/:id/body', ({ params }) =>
        HttpResponse.json({ body: `Body of ${params.id}.` }),
      ),
    )
    const { result } = renderHook(() => useReveal())

    await act(async () => {
      await result.current.expand({ id: 'p1', has_full_body: true })
      await result.current.expand({ id: 'p2', has_full_body: true })
    })
    act(() => result.current.collapse('p1'))

    expect(result.current.isExpanded('p1')).toBe(false)
    expect(result.current.isExpanded('p2')).toBe(true)
  })
})

describe('useMe', () => {
  it('loads the member and roster', async () => {
    server.use(
      http.get('/api/me', () =>
        HttpResponse.json({ member: 'Ada', members: ['Ada', 'Grace'], reader_index: 0 }),
      ),
    )
    const { result } = renderHook(() => useMe())
    await waitFor(() => expect(result.current.member).toBe('Ada'))
    expect(result.current.members).toEqual(['Ada', 'Grace'])
    expect(result.current.readerIndex).toBe(0)
  })

  it('exposes an error when identity cannot load', async () => {
    server.use(http.get('/api/me', () => HttpResponse.error()))
    const { result } = renderHook(() => useMe())
    await waitFor(() => expect(result.current.error).toBeTruthy())
    expect(result.current.loading).toBe(false)
  })
})

describe('useToggleSet', () => {
  it('starts from the ids it was given', () => {
    const { result } = renderHook(() => useToggleSet(['p1']))
    expect(result.current.has('p1')).toBe(true)
    expect(result.current.has('p2')).toBe(false)
  })

  it('flips one id without touching the others', () => {
    const { result } = renderHook(() => useToggleSet())
    act(() => result.current.toggle('p1'))
    expect(result.current.has('p1')).toBe(true)
    expect(result.current.has('p2')).toBe(false)
  })

  it('flips back', () => {
    const { result } = renderHook(() => useToggleSet(['p1']))
    act(() => result.current.toggle('p1'))
    expect(result.current.has('p1')).toBe(false)
    expect(result.current.size).toBe(0)
  })
})

describe('usePanels', () => {
  beforeEach(() => window.localStorage.clear())

  it('opens a panel it has never heard of', () => {
    const { result } = renderHook(() => usePanels())
    expect(result.current.isOpen('book')).toBe(true)
  })

  it('closes on toggle', () => {
    const { result } = renderHook(() => usePanels())
    act(() => result.current.toggle('book'))
    expect(result.current.isOpen('book')).toBe(false)
  })

  it('reopens on a second toggle', () => {
    const { result } = renderHook(() => usePanels())
    act(() => result.current.toggle('book'))
    act(() => result.current.toggle('book'))
    expect(result.current.isOpen('book')).toBe(true)
  })

  it('remembers a collapse across a remount', () => {
    const first = renderHook(() => usePanels())
    act(() => first.result.current.toggle('book'))
    first.unmount()

    const { result } = renderHook(() => usePanels())
    expect(result.current.isOpen('book')).toBe(false)
  })

  it('honours a default of closed', () => {
    const { result } = renderHook(() => usePanels({ progress: false }))
    expect(result.current.isOpen('progress')).toBe(false)
    expect(result.current.isOpen('book')).toBe(true)
  })

  it('opens a panel added after the stored map was written', () => {
    window.localStorage.setItem('bookclub.panels', JSON.stringify({ book: false }))
    const { result } = renderHook(() => usePanels())
    expect(result.current.isOpen('filter')).toBe(true)
  })
})

describe('useTheme', () => {
  let media

  function stubMatchMedia(matches) {
    const listeners = new Set()
    const query = {
      matches,
      addEventListener: (_event, fn) => listeners.add(fn),
      removeEventListener: (_event, fn) => listeners.delete(fn),
    }
    window.matchMedia = vi.fn(() => query)
    return {
      change(next) {
        query.matches = next
        listeners.forEach((fn) => fn({ matches: next }))
      },
      get listeners() {
        return listeners
      },
    }
  }

  beforeEach(() => {
    window.localStorage.clear()
    media = stubMatchMedia(false)
  })

  afterEach(() => {
    delete window.matchMedia
  })

  it('follows the system when nothing has been chosen', () => {
    media = stubMatchMedia(true)
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
    expect(result.current.followsSystem).toBe(true)
  })

  it('paints the theme onto the document element', () => {
    const { result } = renderHook(() => useTheme())
    expect(document.documentElement.dataset.theme).toBe('light')
    act(() => result.current.toggle())
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('toggles between the two', () => {
    const { result } = renderHook(() => useTheme())
    act(() => result.current.toggle())
    expect(result.current.isDark).toBe(true)
    act(() => result.current.toggle())
    expect(result.current.isDark).toBe(false)
  })

  it('keeps following the system until the member decides', () => {
    const { result } = renderHook(() => useTheme())
    act(() => media.change(true))
    expect(result.current.theme).toBe('dark')
  })

  it('stops following the system once the member decides', () => {
    const { result } = renderHook(() => useTheme())
    act(() => result.current.setTheme('light'))
    act(() => media.change(true))
    expect(result.current.theme).toBe('light')
    expect(result.current.followsSystem).toBe(false)
  })

  it('remembers the choice across a remount', () => {
    const first = renderHook(() => useTheme())
    act(() => first.result.current.setTheme('dark'))
    first.unmount()

    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
    expect(result.current.followsSystem).toBe(false)
  })

  it('stops listening when it unmounts', () => {
    const { unmount } = renderHook(() => useTheme())
    expect(media.listeners.size).toBe(1)
    unmount()
    expect(media.listeners.size).toBe(0)
  })

  it('falls back to light in a browser without matchMedia', () => {
    delete window.matchMedia
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
  })

  it('ignores a stored value that is not a theme', () => {
    window.localStorage.setItem('bookclub.theme', '"chartreuse"')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
  })
})

describe('usePostEditor', () => {
  const short = post({ body_preview: 'A thought.', has_full_body: false })
  const long = post({ id: 'p9', body_preview: 'The first 1,900…', has_full_body: true })

  function bodyRoute(handler) {
    server.use(http.get('/api/posts/:id/body', handler))
  }

  it('opens on the preview when that is the whole post', () => {
    const { result } = renderHook(() => usePostEditor(short))
    expect(result.current.fields.body).toBe('A thought.')
    expect(result.current.loaded).toBe(true)
  })

  it('opens on the fields of the post being edited', () => {
    const { result } = renderHook(() => usePostEditor(short))
    expect(result.current.fields).toMatchObject({ chapter: '9', page: '204' })
  })

  it('leaves the position fields empty when the post has none', () => {
    const { result } = renderHook(() => usePostEditor(post({ position: null })))
    expect(result.current.fields).toMatchObject({ chapter: '', page: '' })
  })

  // Saving body_preview would truncate a long post to its own preview.
  it('will not let a long post be saved before its full body arrives', async () => {
    bodyRoute(() => HttpResponse.json({ body: 'The whole thing.' }))
    const { result } = renderHook(() => usePostEditor(long))

    expect(result.current.canSave).toBe(false)
    await waitFor(() => expect(result.current.loaded).toBe(true))
    expect(result.current.fields.body).toBe('The whole thing.')
    expect(result.current.canSave).toBe(true)
  })

  it('reports a body that will not load', async () => {
    bodyRoute(() => HttpResponse.error())
    const { result } = renderHook(() => usePostEditor(long))
    await waitFor(() => expect(result.current.error).toBeTruthy())
    expect(result.current.canSave).toBe(false)
  })

  it('sends the edited values as numbers', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePostEditor(short, { onSave }))

    act(() => result.current.setField('body', 'Revised.'))
    act(() => result.current.setField('chapter', '11'))
    await act(async () => {
      await result.current.save()
    })

    expect(onSave).toHaveBeenCalledWith({ body: 'Revised.', chapter: 11, page: 204 })
  })

  it('sends null for a position that was cleared', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePostEditor(short, { onSave }))

    act(() => result.current.setField('chapter', ''))
    await act(async () => {
      await result.current.save()
    })

    expect(onSave).toHaveBeenCalledWith({ body: 'A thought.', chapter: null, page: null })
  })

  it('clearing the chapter clears the page with it', () => {
    const { result } = renderHook(() => usePostEditor(short))
    act(() => result.current.setField('chapter', ''))
    expect(result.current.fields.page).toBe('')
  })

  it('keeps the edit on screen when the save fails', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('Notion said no.'))
    const { result } = renderHook(() => usePostEditor(short, { onSave }))

    act(() => result.current.setField('body', 'Revised.'))
    let saved
    await act(async () => {
      saved = await result.current.save()
    })

    expect(saved).toBe(false)
    expect(result.current.error).toBe('Notion said no.')
    expect(result.current.fields.body).toBe('Revised.')
  })
})

describe('useComposer chapter bounds', () => {
  const BOOK = { id: 'b1', title: 'Piranesi', total_chapters: 45 }

  const composerFor = (book = BOOK) =>
    renderHook(() => useComposer({ book, onSubmit: vi.fn() }))

  it('refuses a chapter past the end of the book', async () => {
    const { result } = composerFor()
    act(() => result.current.chooseType('Progress'))
    act(() => result.current.setField('chapter', '99'))

    await act(async () => {
      await result.current.submit()
    })
    expect(result.current.error).toBe(
      'Piranesi has 45 chapters, so there is no chapter 99.',
    )
  })

  it('accepts the last chapter', () => {
    const { result } = composerFor()
    act(() => result.current.chooseType('Progress'))
    act(() => result.current.setField('chapter', '45'))
    expect(result.current.isValid).toBe(true)
  })

  it('refuses one past the last chapter', () => {
    const { result } = composerFor()
    act(() => result.current.chooseType('Progress'))
    act(() => result.current.setField('chapter', '46'))
    expect(result.current.isValid).toBe(false)
  })

  it('does not submit a refused chapter', async () => {
    const onSubmit = vi.fn()
    const { result } = renderHook(() => useComposer({ book: BOOK, onSubmit }))
    act(() => result.current.chooseType('Progress'))
    act(() => result.current.setField('chapter', '99'))

    await act(async () => {
      await result.current.submit()
    })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('accepts any chapter when the book states no length', () => {
    const { result } = composerFor({ title: 'X', total_chapters: null })
    act(() => result.current.chooseType('Progress'))
    act(() => result.current.setField('chapter', '9000'))
    expect(result.current.isValid).toBe(true)
  })

  // Number('abc') is NaN, which serialises to null and reaches the server as a
  // missing chapter with a misleading error.
  it('refuses a chapter that is not a number', () => {
    const { result } = composerFor()
    act(() => result.current.chooseType('Progress'))
    act(() => result.current.setField('chapter', 'abc'))
    expect(result.current.isValid).toBe(false)
  })

  it('bounds a thought as well as a progress update', () => {
    const { result } = composerFor()
    act(() => result.current.chooseType('Thought'))
    act(() => result.current.setField('body', 'A thought.'))
    act(() => result.current.setField('chapter', '99'))
    expect(result.current.isValid).toBe(false)
  })
})

describe('usePostEditor chapter bounds', () => {
  const BOOK = { id: 'b1', title: 'Piranesi', total_chapters: 45 }
  const short = post({ body_preview: 'A thought.', has_full_body: false })

  it('will not save a chapter past the end of the book', async () => {
    const onSave = vi.fn()
    const { result } = renderHook(() => usePostEditor(short, { book: BOOK, onSave }))

    act(() => result.current.setField('chapter', '99'))
    expect(result.current.canSave).toBe(false)

    let saved
    await act(async () => {
      saved = await result.current.save()
    })

    expect(saved).toBe(false)
    expect(onSave).not.toHaveBeenCalled()
    expect(result.current.error).toBe(
      'Piranesi has 45 chapters, so there is no chapter 99.',
    )
  })

  it('saves the last chapter', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePostEditor(short, { book: BOOK, onSave }))

    act(() => result.current.setField('chapter', '45'))
    await act(async () => {
      await result.current.save()
    })
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ chapter: 45 }),
    )
  })
})
