/**
 * "Ch 12 · p.204" | "Ch 12" | null
 *
 * Set in the mono face, positions read as citations, which is what they are.
 */
export function formatPosition(position) {
  if (!position || position.chapter == null) return null
  if (position.page == null) return `Ch ${position.chapter}`
  return `Ch ${position.chapter} · p.${position.page}`
}
