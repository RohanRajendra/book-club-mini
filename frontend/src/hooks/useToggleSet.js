import { useCallback, useState } from 'react'

/**
 * A set of ids that can be flipped one at a time.
 *
 * Used for collapsed reply threads: membership is the exception, so an empty
 * set means everything is in its default state.
 */
export function useToggleSet(initial = []) {
  const [ids, setIds] = useState(() => new Set(initial))

  const has = useCallback((id) => ids.has(id), [ids])

  const toggle = useCallback((id) => {
    setIds((current) => {
      const next = new Set(current)
      // delete reports whether it removed anything, which is the flip.
      if (!next.delete(id)) next.add(id)
      return next
    })
  }, [])

  return { has, toggle, size: ids.size }
}
