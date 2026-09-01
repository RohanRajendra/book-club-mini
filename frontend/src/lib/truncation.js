/**
 * Roughly eight lines at the feed's measure. Below this a post reads as an
 * entry in a feed; above it, one post fills the screen and the feed stops
 * being one.
 */
export const CLAMP_CHARS = 520

/**
 * Whether the feed should show this post short, with a control to open it.
 *
 * Two separate cases end up here. A post over the storage layer's field limit
 * has its remainder in a body block and needs a fetch to show in full. A post
 * under that limit can still be twenty lines long, and clamping it needs no
 * request at all — the text is already on the page.
 */
export function isClampable(post) {
  return Boolean(post.has_full_body) || (post.body_preview?.length ?? 0) > CLAMP_CHARS
}

/** Whether opening it costs a request. */
export function needsFetch(post) {
  return Boolean(post.has_full_body)
}
