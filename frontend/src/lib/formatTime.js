const MINUTE = 60
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** "just now" | "3m ago" | "3h ago" | "2 days ago" */
export function formatRelativeTime(value, now = new Date()) {
  if (!value) return ''
  const seconds = Math.floor((now - new Date(value)) / 1000)

  if (seconds < MINUTE) return 'just now'
  if (seconds < HOUR) return `${Math.floor(seconds / MINUTE)}m ago`
  if (seconds < DAY) return `${Math.floor(seconds / HOUR)}h ago`

  const days = Math.floor(seconds / DAY)
  return days === 1 ? '1 day ago' : `${days} days ago`
}

/** The exact time, shown on hover. */
export function formatExactTime(value) {
  if (!value) return ''
  return new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}
