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
 * `isEstimated` says the far end is a guess — the book is still being read and
 * nobody has said where it ends. It is not a record of whether the number was
 * adjusted: a stated total that a post overshoots is still not an estimate.
 *
 * A finished book with no stated length ends at its furthest posted chapter.
 * Headroom leaves room for chapters not yet reached, and a finished book has
 * none, so adding it draws the last tick short of the end and implies there is
 * more to read.
 */
export function spineScale(totalChapters, observedMax, isFinished = false) {
  const observed = observedMax || 0
  if (totalChapters != null) {
    return { max: Math.max(totalChapters, observed), isEstimated: false }
  }
  if (isFinished && observed) {
    return { max: observed, isEstimated: false }
  }
  return {
    max: Math.max(Math.ceil(observed * HEADROOM), MIN_SCALE),
    isEstimated: true,
  }
}
