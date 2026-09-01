import { useState } from 'react'
import { escapes } from './QuickProgress'

/** A reply, written under the post it answers. */
export function ReplyBox({ post, onSubmit, onCancel }) {
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  return (
    <form
      className="editor editor--reply"
      onKeyDown={escapes(onCancel)}
      onSubmit={async (event) => {
        event.preventDefault()
        if (!body.trim()) return
        setBusy(true)
        try {
          await onSubmit(body)
        } finally {
          setBusy(false)
        }
      }}
    >
      <label className="sr-only" htmlFor={`reply-body-${post.id}`}>
        Reply to {post.member}
      </label>
      <textarea
        id={`reply-body-${post.id}`}
        autoFocus
        placeholder={`Reply to ${post.member}…`}
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />
      <div className="composer__footer">
        <span className="spacer" />
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="primary" disabled={busy || !body.trim()}>
          Reply
        </button>
      </div>
    </form>
  )
}
