import { formatPosition } from '../lib/formatPosition'
import { formatExactTime, formatRelativeTime } from '../lib/formatTime'
import { initialOf, readerColourFor } from '../lib/readerColour'
import { BlurOverlay } from './BlurOverlay'

export function PostCard({
  post,
  roster,
  reveal,
  onReply,
  onEdit,
  onDelete,
  replyCount = 0,
  className = 'card',
  children,
}) {
  const colour = readerColourFor(post.member, roster)
  const position = formatPosition(post.position)
  const blurred = post.is_spoiler && !reveal.isRevealed(post.id)
  const body = reveal.bodyFor(post)
  // Read more never appears on a post that is not actually truncated.
  const truncated = post.has_full_body && !reveal.isExpanded(post.id)

  return (
    <article className={className}>
      <header className="card__head" style={{ color: colour }}>
        <span className="initial">
          <span>{initialOf(post.member)}</span>
        </span>
        <span className="card__member">{post.member}</span>
        {position && <span className="mono muted">{position}</span>}
        <span className="mono muted" title={formatExactTime(post.created_at)}>
          {formatRelativeTime(post.created_at)}
        </span>
        {post.was_edited && <span className="mono muted">edited</span>}
      </header>

      {blurred ? (
        <BlurOverlay post={post} onReveal={reveal.reveal} />
      ) : (
        <p className="card__body">
          {body}
          {truncated && (
            <>
              {' '}
              <button type="button" onClick={() => reveal.expand(post.id)}>
                Read more
              </button>
            </>
          )}
        </p>
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

      {children}
    </article>
  )
}
