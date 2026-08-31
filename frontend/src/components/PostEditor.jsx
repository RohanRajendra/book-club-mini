import { usePostEditor } from '../hooks/usePostEditor'
import { escapes } from './QuickProgress'

/**
 * Editing, in the card being edited.
 *
 * It replaces the body of that one post rather than opening below the feed:
 * the point of an edit is the text you are changing, and you cannot revise
 * what has scrolled off the screen.
 */
export function PostEditor({ post, onSave, onCancel }) {
  const editor = usePostEditor(post, { onSave })
  const { fields, setField } = editor

  return (
    <form
      className="editor"
      onKeyDown={escapes(onCancel)}
      onSubmit={(event) => {
        event.preventDefault()
        editor.save()
      }}
    >
      <div className="composer__row">
        <label className="sr-only" htmlFor={`edit-chapter-${post.id}`}>
          Chapter
        </label>
        <input
          id={`edit-chapter-${post.id}`}
          inputMode="numeric"
          placeholder="Chapter"
          value={fields.chapter}
          onChange={(event) => setField('chapter', event.target.value)}
        />
        <label className="sr-only" htmlFor={`edit-page-${post.id}`}>
          Page
        </label>
        <input
          id={`edit-page-${post.id}`}
          inputMode="numeric"
          placeholder="Page"
          value={fields.page}
          onChange={(event) => setField('page', event.target.value)}
        />
      </div>

      <label className="sr-only" htmlFor={`edit-body-${post.id}`}>
        Post
      </label>
      <textarea
        id={`edit-body-${post.id}`}
        autoFocus
        value={fields.body}
        onChange={(event) => setField('body', event.target.value)}
      />

      <div className="composer__footer">
        {!editor.loaded && <span className="mono muted">Loading the full post…</span>}
        {editor.error && <span className="muted">{editor.error}</span>}
        <span className="spacer" />
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="primary" disabled={!editor.canSave}>
          {editor.saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  )
}
