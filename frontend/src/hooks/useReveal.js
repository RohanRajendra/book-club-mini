import { useCallback, useState } from 'react'
import { api } from '../lib/api'

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

  const expand = useCallback(async (postId) => {
    // Read more fetches the full body on click. It never appears on a post
    // that is not actually truncated, so this is only ever a real fetch.
    const { body } = await api.postBody(postId)
    setBodies((current) => ({ ...current, [postId]: body }))
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
