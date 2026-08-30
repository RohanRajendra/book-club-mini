import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

/** Chip label → the PostType it keeps. `all` keeps everything. */
export const FILTERS = {
  all: null,
  progress: 'Progress',
  thought: 'Thought',
  question: 'Question',
}

/**
 * The feed: load, refresh, filter, error.
 *
 * Filtering is client-side. The response carries counts for all four chips, so
 * filtering server-side would cost the counts of the types it filtered out —
 * and a chip click would cost a request.
 */
export function useFeed(bookId, { as } = {}) {
  const [feed, setFeed] = useState(null)
  const [filter, setFilter] = useState('all')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const inFlight = useRef(false)

  const load = useCallback(async () => {
    if (!bookId) return
    // What stops a fast alt-tab loop from stacking requests.
    if (inFlight.current) return

    inFlight.current = true
    setLoading(true)
    try {
      const next = await api.feed(bookId, { as })
      setFeed(next)
      setError(null)
    } catch (caught) {
      // Refreshing never blanks the feed: `feed` is left alone, so the last
      // loaded content stays on screen behind the error.
      setError(caught.message)
    } finally {
      inFlight.current = false
      setLoading(false)
    }
  }, [bookId, as])

  useEffect(() => {
    setFeed(null)
    load()
  }, [bookId, as]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onFocus = () => load()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [load])

  const posts = applyFilter(feed?.posts ?? [], filter)

  return {
    feed,
    posts,
    counts: feed?.counts ?? { all: 0, progress: 0, thought: 0, question: 0 },
    positions: feed?.positions ?? [],
    spine: feed?.spine ?? null,
    book: feed?.book ?? null,
    filter,
    setFilter,
    loading,
    error,
    refresh: load,
    /** Optimistic insert; reconciled or removed by the caller. */
    insertPost: (post) =>
      setFeed((current) =>
        current ? { ...current, posts: [post, ...current.posts] } : current,
      ),
    removePost: (postId) =>
      setFeed((current) =>
        current
          ? { ...current, posts: current.posts.filter((p) => p.id !== postId) }
          : current,
      ),
  }
}

function applyFilter(posts, filter) {
  const wanted = FILTERS[filter]
  if (!wanted) return posts
  // Applies to top-level posts only; replies stay attached to whatever
  // survives the filter.
  return posts.filter((post) => post.type === wanted)
}
