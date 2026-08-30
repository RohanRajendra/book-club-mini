import { useEffect, useState } from 'react'

import { BookBar } from './components/BookBar'
import { BookForm } from './components/BookForm'
import { Composer } from './components/Composer'
import { Feed } from './components/Feed'
import { FilterChips } from './components/FilterChips'
import { QuickProgress } from './components/QuickProgress'
import { Spine } from './components/Spine'
import { useBooks } from './hooks/useBooks'
import { useComposer } from './hooks/useComposer'
import { useFeed } from './hooks/useFeed'
import { useMe } from './hooks/useMe'
import { useReveal } from './hooks/useReveal'
import { api } from './lib/api'

import './styles/tokens.css'
import './styles/app.css'

export default function App() {
  const me = useMe()
  const books = useBooks()
  const [viewer, setViewer] = useState(null)
  const [bookForm, setBookForm] = useState(null) // null | 'add' | book
  const [quickOpen, setQuickOpen] = useState(false)
  const [replyingTo, setReplyingTo] = useState(null)
  const [editing, setEditing] = useState(null)
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    if (me.member && viewer === null) setViewer(me.member)
  }, [me.member, viewer])

  const feed = useFeed(books.selectedId, {
    as: viewer && viewer !== me.member ? viewer : undefined,
  })
  const reveal = useReveal()

  const viewerPosition =
    feed.positions.find((entry) => entry.member === viewer)?.position ?? null

  const composer = useComposer({
    viewerPosition,
    onSubmit: async (values) => {
      const created = await api.createPost({ book_id: books.selectedId, ...values })
      // Optimistic: show it immediately, then reconcile against the server.
      feed.insertPost({ ...created, replies: [] })
      feed.refresh()
      return created
    },
  })

  if (me.error) {
    return (
      <main className="app">
        <p className="notice">{me.error}</p>
      </main>
    )
  }

  async function reply(parentPost, values) {
    await api.createPost({
      book_id: books.selectedId,
      type: 'Thought',
      body: values.body,
      parent_post_id: parentPost.id,
    })
    setReplyingTo(null)
    await feed.refresh()
  }

  async function saveEdit(post, values) {
    await api.editPost(post.id, values)
    setEditing(null)
    await feed.refresh()
  }

  async function remove(post, replyCount) {
    const also = replyCount
      ? ` Its ${replyCount} ${replyCount === 1 ? 'reply goes' : 'replies go'} too.`
      : ''
    if (!window.confirm(`Delete this post?${also}`)) return
    try {
      await api.deletePost(post.id)
      await feed.refresh()
    } catch (caught) {
      setNotice(caught.message)
    }
  }

  return (
    <main className="app">
      <BookBar
        book={books.book}
        books={books.books}
        onSelect={books.select}
        onAdd={() => setBookForm('add')}
        onEdit={(book) => setBookForm(book)}
        onRefresh={feed.refresh}
        refreshing={feed.loading}
        member={me.member}
        members={me.members}
        viewer={viewer ?? me.member ?? ''}
        onViewAs={setViewer}
      />

      {bookForm && (
        <BookForm
          book={bookForm === 'add' ? null : bookForm}
          onCancel={() => setBookForm(null)}
          onSave={async (payload) => {
            if (bookForm === 'add') await books.addBook(payload)
            else await books.updateBook(bookForm.id, payload)
            setBookForm(null)
          }}
        />
      )}

      {/* Keep the last-loaded feed on screen behind any error. */}
      {(feed.error || books.error || notice) && (
        <p className="notice">{feed.error || books.error || notice}</p>
      )}

      {!books.loading && !books.books.length && (
        <p className="empty muted">No books yet. Add the one you're reading.</p>
      )}

      {books.book && (
        <>
          <Spine
            positions={feed.positions}
            spine={feed.spine}
            roster={me.members}
            viewer={viewer ?? me.member}
            onQuickProgress={() => setQuickOpen(true)}
          />

          {quickOpen && (
            <QuickProgress
              onCancel={() => setQuickOpen(false)}
              onSubmit={async (values) => {
                await api.createPost({
                  book_id: books.selectedId,
                  type: 'Progress',
                  body: '',
                  ...values,
                })
                setQuickOpen(false)
                await feed.refresh()
              }}
            />
          )}

          {!viewerPosition && feed.posts.length > 0 && (
            <p className="muted">Post a progress update to start hiding spoilers.</p>
          )}

          {composer.open ? (
            <Composer composer={composer} onCancel={composer.cancel} />
          ) : (
            <button type="button" className="primary" onClick={() => composer.setOpen(true)}>
              New post
            </button>
          )}

          <FilterChips
            filter={feed.filter}
            setFilter={feed.setFilter}
            counts={feed.counts}
          />

          <Feed
            posts={feed.posts}
            roster={me.members}
            reveal={reveal}
            filter={feed.filter}
            onReply={(post) => setReplyingTo(post.id)}
            onEdit={(post) => setEditing(post)}
            onDelete={remove}
            replyingTo={replyingTo}
            renderReplyBox={(post) => (
              <InlineBody
                placeholder="Reply…"
                onCancel={() => setReplyingTo(null)}
                onSubmit={(body) => reply(post, { body })}
              />
            )}
          />

          {editing && (
            <EditDialog
              post={editing}
              onCancel={() => setEditing(null)}
              onSave={(values) => saveEdit(editing, values)}
            />
          )}
        </>
      )}
    </main>
  )
}

function InlineBody({ placeholder, onSubmit, onCancel }) {
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  return (
    <form
      className="composer"
      onKeyDown={(event) => event.key === 'Escape' && onCancel()}
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
      <label className="sr-only" htmlFor="reply-body">
        {placeholder}
      </label>
      <textarea
        id="reply-body"
        autoFocus
        placeholder={placeholder}
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

function EditDialog({ post, onSave, onCancel }) {
  const [body, setBody] = useState(post.body_preview)
  const [chapter, setChapter] = useState(
    post.position?.chapter != null ? String(post.position.chapter) : '',
  )
  const [page, setPage] = useState(
    post.position?.page != null ? String(post.position.page) : '',
  )
  const [loaded, setLoaded] = useState(!post.has_full_body)

  // Edit pre-loads the full body, fetching it first if the post is long.
  useEffect(() => {
    if (post.has_full_body) {
      api.postBody(post.id).then(({ body: full }) => {
        setBody(full)
        setLoaded(true)
      })
    }
  }, [post])

  return (
    <form
      className="dialog"
      onKeyDown={(event) => event.key === 'Escape' && onCancel()}
      onSubmit={(event) => {
        event.preventDefault()
        onSave({
          body,
          chapter: chapter.trim() ? Number(chapter) : null,
          page: page.trim() ? Number(page) : null,
        })
      }}
    >
      <div className="composer__row">
        <input
          inputMode="numeric"
          placeholder="Chapter"
          value={chapter}
          onChange={(event) => setChapter(event.target.value)}
        />
        <input
          inputMode="numeric"
          placeholder="Page"
          value={page}
          onChange={(event) => setPage(event.target.value)}
        />
      </div>
      <textarea value={body} onChange={(event) => setBody(event.target.value)} />
      <div className="composer__footer">
        <span className="spacer" />
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="primary" disabled={!loaded}>
          Save
        </button>
      </div>
    </form>
  )
}
