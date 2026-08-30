import { useState } from 'react'
import { escapes } from './QuickProgress'

const STATUSES = ['Currently Reading', 'Upcoming', 'Paused', 'Finished']

/** Add and edit share this form. A title is the only required field. */
export function BookForm({ book, onSave, onCancel }) {
  const [title, setTitle] = useState(book?.title ?? '')
  const [author, setAuthor] = useState(book?.author ?? '')
  const [status, setStatus] = useState(book?.status ?? 'Currently Reading')
  const [totalChapters, setTotalChapters] = useState(
    book?.total_chapters != null ? String(book.total_chapters) : '',
  )
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!title.trim()) {
      setError('A book needs a title.')
      return
    }
    setBusy(true)
    try {
      await onSave({
        title: title.trim(),
        author: author.trim() || null,
        status,
        total_chapters: totalChapters.trim() ? Number(totalChapters) : null,
      })
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="dialog" onSubmit={handleSubmit} onKeyDown={escapes(onCancel)}>
      <div className="dialog__grid">
        <label className="wide">
          Title
          <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="wide">
          Author
          <input value={author} onChange={(e) => setAuthor(e.target.value)} />
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label>
          Total chapters
          <input
            inputMode="numeric"
            placeholder="Optional"
            value={totalChapters}
            onChange={(e) => setTotalChapters(e.target.value)}
          />
        </label>
      </div>

      <div className="composer__footer">
        {error && <span className="muted">{error}</span>}
        <span className="spacer" />
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="primary" disabled={busy}>
          {book ? 'Save' : 'Add book'}
        </button>
      </div>
    </form>
  )
}
