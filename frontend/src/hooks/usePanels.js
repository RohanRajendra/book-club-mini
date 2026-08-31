import { useCallback, useState } from 'react'
import { readSetting, writeSetting } from '../lib/storage'

export const PANELS_KEY = 'panels'

/**
 * Which rail panels are open.
 *
 * Persisted, because a collapse that resets on reload is not a preference. A
 * panel is open unless it is explicitly recorded as closed, so a panel added
 * later appears for members who already have a stored map.
 */
export function usePanels(defaults = {}) {
  const [state, setState] = useState(() => ({
    ...defaults,
    ...readSetting(PANELS_KEY, {}),
  }))

  const isOpen = useCallback((id) => state[id] !== false, [state])

  const toggle = useCallback((id) => {
    setState((current) => {
      const next = { ...current, [id]: current[id] === false }
      writeSetting(PANELS_KEY, next)
      return next
    })
  }, [])

  return { isOpen, toggle }
}
