import { readerColourFor } from '../lib/readerColour'
import { Chevron } from './Chevron'
import { PostCard } from './PostCard'

/**
 * One level, oldest first — a conversation reads downward inside a feed that
 * reads upward. Indented behind a hairline in the replier's colour.
 *
 * Collapsible, and open by default: a thread of two is not clutter, but a
 * thread you have already read is.
 */
export function ReplyList({
  parentId,
  replies,
  roster,
  reveal,
  onEdit,
  onDelete,
  collapsed = false,
  onToggle,
  editingId,
  renderEditor,
}) {
  if (!replies.length) return null

  const listId = `replies-${parentId}`

  return (
    <div className="thread">
      <button
        type="button"
        className="thread__toggle"
        aria-expanded={!collapsed}
        aria-controls={listId}
        onClick={() => onToggle(parentId)}
      >
        <Chevron className="chevron thread__chevron" />
        {replies.length} {replies.length === 1 ? 'reply' : 'replies'}
      </button>

      <div
        id={listId}
        className="replies"
        hidden={collapsed}
        style={{ color: readerColourFor(replies[0].member, roster) }}
      >
        {replies.map((reply) => (
          <PostCard
            key={reply.id}
            post={reply}
            roster={roster}
            reveal={reveal}
            onEdit={onEdit}
            onDelete={onDelete}
            editing={editingId === reply.id}
            renderEditor={renderEditor}
            className="card reply"
          />
        ))}
      </div>
    </div>
  )
}
