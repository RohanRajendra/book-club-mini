import { formatPosition } from '../lib/formatPosition'
import { formatRelativeTime } from '../lib/formatTime'
import { readerColourFor } from '../lib/readerColour'

/**
 * The single bold element: chapter one at one end, the book's end at the other.
 *
 * Everything past *your own* tick carries the blur wash, so the spine explains
 * the blur rule without copy.
 *
 * Ticks carry no text. Two members at the same chapter would overlap their own
 * labels, so the names live in the legend below and the track stays a track.
 * Orientation is the stylesheet's business — the position of a tick is written
 * as `--pos` and the rail reads it as a distance down, the stacked layout as a
 * distance across.
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
        <>
          <div
            className={`spine__track${spine.is_estimated ? ' spine__track--estimated' : ''}`}
          >
            <span className="spine__cap spine__cap--start mono muted">Ch 1</span>

            {viewerPercent != null && (
              <div className="spine__ahead" style={{ '--pos': `${viewerPercent}%` }} />
            )}

            {positions.map((entry) => (
              <Tick
                key={entry.member}
                entry={entry}
                roster={roster}
                maxChapter={spine.max_chapter}
                isViewer={entry.member === viewer}
                onQuickProgress={onQuickProgress}
              />
            ))}

            <span className="spine__cap spine__cap--end mono muted">
              {spine.is_estimated ? '?' : `Ch ${spine.max_chapter}`}
            </span>
          </div>

          <ul className="spine__legend">
            {positions.map((entry) => (
              <Reader
                key={entry.member}
                entry={entry}
                roster={roster}
                isViewer={entry.member === viewer}
                when={lastPostAt?.[entry.member]}
              />
            ))}
          </ul>
        </>
      )}

      <button type="button" className="spine__update" onClick={onQuickProgress}>
        Update progress
      </button>
    </section>
  )
}

function Tick({ entry, roster, maxChapter, isViewer, onQuickProgress }) {
  const started = Boolean(entry.position)
  const percent = started ? percentOf(entry.position, maxChapter) : 0
  const label = started ? formatPosition(entry.position) : "Hasn't started"

  return (
    <button
      type="button"
      className={`spine__tick${isViewer ? ' spine__tick--own' : ''}`}
      style={{
        '--pos': `${percent}%`,
        color: started ? readerColourFor(entry.member, roster) : 'var(--muted)',
      }}
      onClick={isViewer ? onQuickProgress : undefined}
      disabled={!isViewer}
      aria-label={isViewer ? `You: ${label}. Post progress` : `${entry.member}: ${label}`}
    >
      <span className="spine__mark" />
    </button>
  )
}

function Reader({ entry, roster, isViewer, when }) {
  const started = Boolean(entry.position)

  return (
    <li
      className="spine__reader"
      style={{ color: started ? readerColourFor(entry.member, roster) : 'var(--muted)' }}
    >
      <span className="spine__dot" aria-hidden="true" />
      <span className="spine__who">
        {entry.member}
        {isViewer && <span className="muted"> (you)</span>}
      </span>
      <span className="spine__where mono muted">
        {started ? formatPosition(entry.position) : 'Not started'}
        {/* A time against "Not started" would read as a contradiction. */}
        {started && when && ` · ${formatRelativeTime(when)}`}
      </span>
    </li>
  )
}

function percentOf(position, maxChapter) {
  if (!position || !maxChapter) return null
  // Chapter 1 sits at the start of the track, the last chapter at the end.
  const span = Math.max(maxChapter - 1, 1)
  const along = Math.min(Math.max(position.chapter - 1, 0), span)
  return (along / span) * 100
}
