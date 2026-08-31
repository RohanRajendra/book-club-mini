import { useCallback, useState } from 'react'
import { api } from '../lib/api'
import { needsFetch } from '../lib/truncation'

/**
 * Per-post reveal and expand state.
 *
 * Deliberately component-local and not persisted: revealing affects one post
 * and resets on reload.
 */
export function useReveal() {
  const [revealed, setRevealed] = useState(() => new Set())
  const [bodies, setBodies] = useState({})

  const reveal = useCallback((postId) => {
    setRevealed((current) => new Set(current).add(postId))
  }, [])

  const isRevealed = useCallback((postId) => revealed.has(postId), [revealed])

  /**
   * Show the whole post.
   *
   * A post whose body exceeded the storage layer's field limit has its
   * remainder elsewhere and has to be fetched. A merely long one is already on
   * the page, and opening it should not cost a request.
   */
  const expand = useCallback(async (post) => {
    if (!needsFetch(post)) {
      setBodies((current) => ({ ...current, [post.id]: post.body_preview }))
      return post.body_preview
    }
    const { body } = await api.postBody(post.id)
    setBodies((current) => ({ ...current, [post.id]: body }))
    return body
  }, [])

  /** Back to the preview. The fetched body is dropped, not cached. */
  const collapse = useCallback((postId) => {
    setBodies((current) => {
      const { [postId]: _dropped, ...rest } = current
      return rest
    })
  }, [])

  const bodyFor = useCallback((post) => bodies[post.id] ?? post.body_preview, [bodies])

  const isExpanded = useCallback((postId) => postId in bodies, [bodies])

  return { reveal, isRevealed, expand, collapse, isExpanded, bodyFor }
}
