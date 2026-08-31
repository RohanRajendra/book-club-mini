/**
 * The one component test in the suite.
 *
 * Everything else here tests hooks and helpers, because that is where the
 * logic lives. This file tests none of that: it mounts the whole app against
 * MSW and asserts that the pieces are wired to each other and reachable —
 * three columns present, an editor that opens inside the card it belongs to,
 * disclosures that disclose. Those are the failures that no hook test can see
 * and that nobody notices until they open the page.
 *
 * It queries by role and label, never by class, so a restyle does not break it.
 * Components stay out of the coverage gate.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '../App'
import { server } from './setup'

const post = (o = {}) => ({
  id: 'p1',
  member: 'Ada',
  type: 'Thought',
  body_preview: 'A thought about the statues.',
  has_full_body: false,
  position: { chapter: 9, page: 204 },
  parent_post_id: null,
  created_at: '2026-03-01T12:00:00Z',
  edited_at: '2026-03-01T12:00:00Z',
  was_edited: false,
  is_spoiler: false,
  is_own: true,
  replies: [],
  ...o,
})

beforeEach(() => {
  window.localStorage.clear()
  server.use(
    http.get('/api/me', () =>
      HttpResponse.json({ member: 'Ada', members: ['Ada', 'Grace'], reader_index: 0 }),
    ),
    http.get('/api/books', () =>
      HttpResponse.json([
        {
          id: 'b1',
          title: 'Piranesi',
          author: 'Susanna Clarke',
          status: 'Currently Reading',
          total_chapters: 30,
        },
      ]),
    ),
    http.get('/api/books/:id/feed', () =>
      HttpResponse.json({
        book: {
          id: 'b1',
          title: 'Piranesi',
          author: 'Susanna Clarke',
          status: 'Currently Reading',
          total_chapters: 30,
        },
        posts: [
          post({
            replies: [post({ id: 'r1', member: 'Grace', is_own: false, body_preview: 'A reply.' })],
          }),
          post({ id: 'p2', type: 'Progress', body_preview: '', member: 'Grace', is_own: false }),
        ],
        positions: [
          { member: 'Ada', position: { chapter: 9, page: 204 } },
          { member: 'Grace', position: null },
        ],
        spine: { max_chapter: 30, is_estimated: false },
        counts: { all: 2, progress: 1, thought: 1, question: 0 },
      }),
    ),
  )
})

describe('app', () => {
  it('renders the three columns', async () => {
    render(<App />)
    await screen.findByRole('heading', { name: 'Piranesi' })
    expect(screen.getByText('Susanna Clarke')).toBeDefined()
    expect(screen.getByRole('group', { name: 'Filter posts' })).toBeDefined()
    expect(await screen.findByLabelText('Reading positions')).toBeDefined()
    expect(await screen.findByText('A thought about the statues.')).toBeDefined()
    const spine = screen.getByLabelText('Reading positions')
    expect(within(spine).getByText(/Ch 9 · p\.204/)).toBeDefined()
    expect(within(spine).getByText('Not started')).toBeDefined()
  })

  it('opens the editor inside the card being edited', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('A thought about the statues.')

    const card = screen.getByText('A thought about the statues.').closest('article')
    await user.click(within(card).getByRole('button', { name: 'Edit' }))

    const textarea = within(card).getByLabelText('Post')
    expect(textarea.value).toBe('A thought about the statues.')
    // The card it belongs to is the one that was clicked, not the page bottom.
    expect(card.contains(textarea)).toBe(true)
  })

  it('collapses a reply thread', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('A reply.')

    const toggle = screen.getByRole('button', { name: /1 reply/ })
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    await user.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    // `hidden` is what takes the replies out of the tab order too.
    expect(document.getElementById('replies-p1').hidden).toBe(true)
  })

  it('collapses a rail panel and remembers it', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('heading', { name: 'Piranesi' })

    const toggle = screen.getByRole('button', { name: /Book/ })
    await user.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(document.getElementById('panel-book').hidden).toBe(true)
    expect(JSON.parse(localStorage.getItem('bookclub.panels'))).toEqual({ book: false })
  })

  it('switches to dark', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('heading', { name: 'Piranesi' })

    expect(document.documentElement.dataset.theme).toBe('light')
    await user.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
  })

  it('opens the book form as a modal over the page', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByRole('heading', { name: 'Piranesi' })

    await user.click(screen.getByRole('button', { name: 'Edit book' }))
    const dialog = screen.getByRole('dialog', { name: 'Edit book' })
    expect(within(dialog).getByDisplayValue('Piranesi')).toBeDefined()
  })
})
