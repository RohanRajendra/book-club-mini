import { readerColourFor } from '../lib/readerColour'
import { PostCard } from './PostCard'

/**
 * One level, oldest first — a conversation reads downward inside a feed that
 * reads upward. Indented behind a hairline in the replier's colour.
 */
export function ReplyList({ replies, roster, reveal, onEdit, onDelete }) {
  if (!replies.length) return null

  return (
    <div
      className="replies"
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
          className="card reply"
        />
      ))}
    </div>
  )
}
