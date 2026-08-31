import { useCallback, useEffect, useState } from 'react'
import { readSetting, writeSetting } from '../lib/storage'

export const THEME_KEY = 'theme'
export const DARK_QUERY = '(prefers-color-scheme: dark)'

/** What the operating system is currently asking for. */
export function systemTheme() {
  try {
    return window.matchMedia?.(DARK_QUERY)?.matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

/**
 * The theme to paint before React runs.
 *
 * `index.html` runs the same rule inline in the document head. Without it the
 * page paints light and then flips, which is worse than no dark mode at all.
 */
export function initialTheme() {
  const stored = readSetting(THEME_KEY)
  return stored === 'dark' || stored === 'light' ? stored : systemTheme()
}

/**
 * Light or dark, and who decided.
 *
 * Until the member touches the toggle the app follows the operating system and
 * keeps following it — a laptop that dims at sunset should take the app with
 * it. The first toggle is a decision, so it is stored and the system is no
 * longer consulted.
 */
export function useTheme() {
  const [theme, setThemeState] = useState(initialTheme)
  const [followsSystem, setFollowsSystem] = useState(() => readSetting(THEME_KEY) === null)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    if (!followsSystem) return undefined
    const media = window.matchMedia?.(DARK_QUERY)
    if (!media?.addEventListener) return undefined

    const onChange = (event) => setThemeState(event.matches ? 'dark' : 'light')
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [followsSystem])

  const setTheme = useCallback((next) => {
    setThemeState(next)
    setFollowsSystem(false)
    writeSetting(THEME_KEY, next)
  }, [])

  const toggle = useCallback(
    () => setTheme(theme === 'dark' ? 'light' : 'dark'),
    [theme, setTheme],
  )

  return { theme, isDark: theme === 'dark', setTheme, toggle, followsSystem }
}
