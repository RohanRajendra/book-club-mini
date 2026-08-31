import { formatPosition } from '../lib/formatPosition'
import { formatExactTime, formatRelativeTime } from '../lib/formatTime'
import { initialOf, readerColourFor } from '../lib/readerColour'
import { isClampable } from '../lib/truncation'
import { BlurOverlay } from './BlurOverlay'

/** Thought is the default and Reply is obvious from the indent. */
const BADGED = new Set(['Progress', 'Question'])

export function PostCard({
  post,
  roster,
  reveal,
  onReply,
  onEdit,
  onDelete,
  replyCount = 0,
  editing = false,
  renderEditor,
  className = 'card',
  children,
}) {
  const colour = readerColourFor(post.member, roster)
  const position = formatPosition(post.position)
  const blurred = post.is_spoiler && !reveal.isRevealed(post.id)
  const body = reveal.bodyFor(post)
  const expanded = reveal.isExpanded(post.id)
  const clamped = isClampable(post) && !expanded
  // A progress update carries its whole meaning in the header. Rendering an
  // empty body under it leaves a card that looks like it failed to load.
  const marker = !blurred && !editing && !body.trim()

  return (
    <article className={cardClass(className, { editing, marker })}>
      <header className="card__head" style={{ color: colour }}>
        <span className="initial">
          <span>{initialOf(post.member)}</span>
        </span>
        <span className="card__member">{post.member}</span>
        {BADGED.has(post.type) && <span className="card__type mono">{post.type}</span>}
        {position && <span className="mono muted">{position}</span>}
        <span className="mono muted" title={formatExactTime(post.created_at)}>
          {formatRelativeTime(post.created_at)}
        </span>
        {post.was_edited && <span className="mono muted">edited</span>}
      </header>

      {editing ? (
        renderEditor(post)
      ) : (
        <>
          {blurred && <BlurOverlay post={post} onReveal={reveal.reveal} />}

          {!blurred && !marker && (
            <div className="card__text">
              <p className={clamped ? 'card__body card__body--clamped' : 'card__body'}>
                {body}
              </p>
              {isClampable(post) && (
                <button
                  type="button"
                  className="linkbutton"
                  onClick={() => (expanded ? reveal.collapse(post.id) : reveal.expand(post))}
                >
                  {expanded ? 'Show less' : 'Read more'}
                </button>
              )}
            </div>
          )}

          <div className="card__actions">
            {onReply && (
              <button type="button" onClick={() => onReply(post)}>
                Reply
              </button>
            )}
            {post.is_own && onEdit && (
              <button type="button" onClick={() => onEdit(post)}>
                Edit
              </button>
            )}
            {post.is_own && onDelete && (
              <button
                type="button"
                className="danger"
                onClick={() => onDelete(post, replyCount)}
              >
                Delete
              </button>
            )}
          </div>
        </>
      )}

      {children}
    </article>
  )
}

function cardClass(base, { editing, marker }) {
  return [base, editing && 'card--editing', marker && 'card--marker']
    .filter(Boolean)
    .join(' ')
}
