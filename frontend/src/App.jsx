import { useEffect, useMemo, useState } from 'react'

import { BookForm } from './components/BookForm'
import { BookPanel } from './components/BookPanel'
import { Composer } from './components/Composer'
import { Feed } from './components/Feed'
import { FilterChips } from './components/FilterChips'
import { Panel } from './components/Panel'
import { PostEditor } from './components/PostEditor'
import { QuickProgress } from './components/QuickProgress'
import { ReplyBox } from './components/ReplyBox'
import { SignIn } from './components/SignIn'
import { Spine } from './components/Spine'
import { TopBar } from './components/TopBar'
import { useBooks } from './hooks/useBooks'
import { useComposer } from './hooks/useComposer'
import { useFeed } from './hooks/useFeed'
import { useMe } from './hooks/useMe'
import { usePanels } from './hooks/usePanels'
import { useReveal } from './hooks/useReveal'
import { useTheme } from './hooks/useTheme'
import { useToggleSet } from './hooks/useToggleSet'
import { api } from './lib/api'
import { lastProgressAt } from './lib/lastProgressAt'

import './styles/tokens.css'
import './styles/app.css'

export default function App() {
  const me = useMe()
  const books = useBooks()
  const theme = useTheme()
  const panels = usePanels()
  const threads = useToggleSet()

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

  const lastPostAt = useMemo(
    () => lastProgressAt(feed.feed?.posts ?? []),
    [feed.feed],
  )

  const composer = useComposer({
    viewerPosition,
    book: books.book,
    onSubmit: async (values) => {
      const created = await api.createPost({ book_id: books.selectedId, ...values })
      // Optimistic: show it immediately, then reconcile against the server.
      feed.insertPost({ ...created, replies: [] })
      feed.refresh()
      return created
    },
  })

  // Before anything else: a browser with no session has no feed to show, and
  // every request it could make would come back 401.
  if (me.needsSignIn) {
    return <SignIn onSignIn={me.signIn} />
  }

  if (me.error) {
    return (
      <div className="shell">
        <p className="notice">{me.error}</p>
      </div>
    )
  }

  async function reply(parentPost, body) {
    await api.createPost({
      book_id: books.selectedId,
      type: 'Thought',
      body,
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

  const problem = feed.error || books.error || notice

  return (
    <div className="shell">
      <TopBar
        member={me.member}
        members={me.members}
        viewer={viewer ?? me.member ?? ''}
        onViewAs={setViewer}
        onRefresh={feed.refresh}
        refreshing={feed.loading}
        theme={theme.theme}
        onToggleTheme={theme.toggle}
        onSignOut={me.signedIn ? me.signOut : undefined}
      />

      <div className="columns">
        <aside className="rail rail--left">
          <Panel
            id="book"
            title="Book"
            open={panels.isOpen('book')}
            onToggle={panels.toggle}
          >
            <BookPanel
              book={books.book}
              books={books.books}
              onSelect={books.select}
              onAdd={() => setBookForm('add')}
              onEdit={(book) => setBookForm(book)}
            />
          </Panel>

          {books.book && (
            <Panel
              id="filter"
              title="Filter"
              badge={feed.counts.all}
              open={panels.isOpen('filter')}
              onToggle={panels.toggle}
            >
              <FilterChips
                filter={feed.filter}
                setFilter={feed.setFilter}
                counts={feed.counts}
              />
            </Panel>
          )}
        </aside>

        <main className="column">
          {/* Keep the last-loaded feed on screen behind any error. */}
          {problem && <p className="notice">{problem}</p>}

          {!books.loading && !books.books.length && (
            <p className="empty muted">No books yet. Add the one you're reading.</p>
          )}

          {books.book && (
            <>
              {composer.open ? (
                <Composer composer={composer} onCancel={composer.cancel} />
              ) : (
                <button
                  type="button"
                  className="newpost"
                  onClick={() => composer.setOpen(true)}
                >
                  New post…
                </button>
              )}

              {!viewerPosition && feed.posts.length > 0 && (
                <p className="hint muted">
                  Post a progress update to start hiding spoilers.
                </p>
              )}

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
                  <ReplyBox
                    post={post}
                    onCancel={() => setReplyingTo(null)}
                    onSubmit={(body) => reply(post, body)}
                  />
                )}
                editingId={editing?.id ?? null}
                renderEditor={(post) => (
                  <PostEditor
                    post={post}
                    book={books.book}
                    onCancel={() => setEditing(null)}
                    onSave={(values) => saveEdit(post, values)}
                  />
                )}
                threads={threads}
              />
            </>
          )}
        </main>

        <aside className="rail rail--right">
          {books.book && (
            <Panel
              id="progress"
              title="Progress"
              open={panels.isOpen('progress')}
              onToggle={panels.toggle}
            >
              <Spine
                positions={feed.positions}
                spine={feed.spine}
                roster={me.members}
                viewer={viewer ?? me.member}
                lastPostAt={lastPostAt}
                onQuickProgress={() => setQuickOpen(true)}
              />

              {quickOpen && (
                <QuickProgress
                  book={books.book}
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
            </Panel>
          )}
        </aside>
      </div>

      {bookForm && (
        <div className="modal">
          <button
            type="button"
            className="modal__backdrop"
            aria-label="Close"
            onClick={() => setBookForm(null)}
          />
          <div
            className="modal__panel"
            role="dialog"
            aria-modal="true"
            aria-label={bookForm === 'add' ? 'Add book' : 'Edit book'}
          >
            <BookForm
              book={bookForm === 'add' ? null : bookForm}
              onCancel={() => setBookForm(null)}
              onSave={async (payload) => {
                if (bookForm === 'add') await books.addBook(payload)
                else await books.updateBook(bookForm.id, payload)
                setBookForm(null)
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
