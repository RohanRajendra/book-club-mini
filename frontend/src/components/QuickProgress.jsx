import { useState } from 'react'
import { positionProblem } from '../lib/positionRules'

/**
 * The most-used action in the app: it must not require opening the composer.
 * Submittable by keyboard alone.
 */
export function QuickProgress({ onSubmit, onCancel, book, error }) {
  const [chapter, setChapter] = useState('')
  const [page, setPage] = useState('')
  const [busy, setBusy] = useState(false)

  // The most-used action in the app, so it gets the same bound as the
  // composer rather than relying on the server to refuse it.
  const problem = positionProblem({ chapter, page }, book)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!chapter.trim() || problem) return
    setBusy(true)
    try {
      await onSubmit({ chapter: Number(chapter), page: page.trim() ? Number(page) : null })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="quick" onSubmit={handleSubmit} onKeyDown={escapes(onCancel)}>
      <label className="sr-only" htmlFor="quick-chapter">
        Chapter
      </label>
      <input
        id="quick-chapter"
        autoFocus
        inputMode="numeric"
        placeholder="Chapter"
        value={chapter}
        onChange={(event) => setChapter(event.target.value)}
      />
      <label className="sr-only" htmlFor="quick-page">
        Page, optional
      </label>
      <input
        id="quick-page"
        inputMode="numeric"
        placeholder="Page"
        value={page}
        onChange={(event) => setPage(event.target.value)}
      />
      <button
        type="submit"
        className="primary"
        disabled={!chapter.trim() || busy || problem !== null}
      >
        Post
      </button>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
      {(problem || error) && <span className="muted">{problem || error}</span>}
    </form>
  )
}

export function escapes(onCancel) {
  return (event) => {
    if (event.key === 'Escape') onCancel()
  }
}
