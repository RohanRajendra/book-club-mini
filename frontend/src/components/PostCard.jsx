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

  return (
    <article className={editing ? `${className} card--editing` : className}>
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

      {editing ? (
        renderEditor(post)
      ) : (
        <>
          {blurred ? (
            <BlurOverlay post={post} onReveal={reveal.reveal} />
          ) : (
            <p className="card__body">
              {body}
              {/* Never shown on a post that is not actually truncated. */}
              {post.has_full_body && (
                <>
                  {' '}
                  <button
                    type="button"
                    className="linkbutton"
                    onClick={() =>
                      expanded ? reveal.collapse(post.id) : reveal.expand(post.id)
                    }
                  >
                    {expanded ? 'Show less' : 'Read more'}
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
        </>
      )}

      {children}
    </article>
  )
}
