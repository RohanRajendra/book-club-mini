import { formatPosition } from '../lib/formatPosition'
import { formatRelativeTime } from '../lib/formatTime'
import { readerColourFor } from '../lib/readerColour'

/**
 * The single bold element. Chapter 1 at the left, the book's end at the right.
 *
 * Everything to the right of *your own* tick is tinted with the blur wash, so
 * the spine explains the blur rule without copy.
 */
export function Spine({ positions, spine, roster, viewer, lastPostAt, onQuickProgress }) {
  if (!spine) return null

  const anyPosts = positions.some((entry) => entry.position)
  const viewerEntry = positions.find((entry) => entry.member === viewer)
  const viewerPercent = percentOf(viewerEntry?.position, spine.max_chapter)

  return (
    <section className="spine" aria-label="Reading positions">
      {!anyPosts ? (
        <p className="spine__empty muted">Post where you are to start the spine.</p>
      ) : (
        <div
          className={`spine__track${spine.is_estimated ? ' spine__track--estimated' : ''}`}
        >
          {viewerPercent != null && (
            <div
              className="spine__ahead"
              style={{ left: `${viewerPercent}%`, right: 0 }}
            />
          )}

          {positions.map((entry) => (
            <Tick
              key={entry.member}
              entry={entry}
              roster={roster}
              maxChapter={spine.max_chapter}
              isViewer={entry.member === viewer}
              when={lastPostAt?.[entry.member]}
              onQuickProgress={onQuickProgress}
            />
          ))}

          {!spine.is_estimated && (
            <span className="spine__end mono muted">Ch {spine.max_chapter}</span>
          )}
        </div>
      )}
    </section>
  )
}

function Tick({ entry, roster, maxChapter, isViewer, when, onQuickProgress }) {
  const colour = readerColourFor(entry.member, roster)
  const started = Boolean(entry.position)
  const percent = started ? percentOf(entry.position, maxChapter) : 0

  const label = started ? formatPosition(entry.position) : "Hasn't started"

  return (
    <button
      type="button"
      className={`spine__tick${isViewer ? ' spine__tick--own' : ''}`}
      style={{ left: `${percent}%`, color: started ? colour : 'var(--muted)' }}
      onClick={isViewer ? onQuickProgress : undefined}
      disabled={!isViewer}
      aria-label={
        isViewer
          ? `You: ${label}. Post progress`
          : `${entry.member}: ${label}`
      }
    >
      <span className="spine__label mono">{label}</span>
      <span className="spine__mark" />
      {when && <span className="spine__when mono muted">{formatRelativeTime(when)}</span>}
    </button>
  )
}

function percentOf(position, maxChapter) {
  if (!position || !maxChapter) return null
  // Chapter 1 sits at the left edge, the last chapter at the right.
  const span = Math.max(maxChapter - 1, 1)
  const along = Math.min(Math.max(position.chapter - 1, 0), span)
  return (along / span) * 100
}
