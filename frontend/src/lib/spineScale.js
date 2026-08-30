export const MIN_SCALE = 10
export const HEADROOM = 1.2

/**
 * How far the spine's track reaches, and whether that is a guess.
 *
 * Duplicates ScaleCalculator on the backend deliberately: the API sends the
 * computed scale, and this recomputes it locally for the optimistic update
 * after posting. The shared cases keep them honest — if they ever disagree,
 * delete this copy and render only what the API sends.
 *
 * `isEstimated` tracks whether the book told us its length, not whether the
 * number was adjusted: a stated total that a post overshoots is still not an
 * estimate.
 */
export function spineScale(totalChapters, observedMax) {
  const observed = observedMax || 0
  if (totalChapters != null) {
    return { max: Math.max(totalChapters, observed), isEstimated: false }
  }
  return {
    max: Math.max(Math.ceil(observed * HEADROOM), MIN_SCALE),
    isEstimated: true,
  }
}
