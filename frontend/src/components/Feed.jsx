import { PostCard } from './PostCard'
import { ReplyList } from './ReplyList'

const EMPTY_COPY = {
  all: "Nothing here yet. Post where you are, or what you're thinking.",
  progress: 'No progress posts yet.',
  thought: 'No thoughts yet.',
  question: 'No questions yet.',
}

export function Feed({
  posts,
  roster,
  reveal,
  filter,
  onReply,
  onEdit,
  onDelete,
  replyingTo,
  renderReplyBox,
  editingId,
  renderEditor,
  threads,
}) {
  if (!posts.length) {
    return <p className="empty muted">{EMPTY_COPY[filter] ?? EMPTY_COPY.all}</p>
  }

  return (
    <div className="feed">
      {posts.map((post) => (
        <PostCard
          key={post.id}
          post={post}
          roster={roster}
          reveal={reveal}
          onReply={onReply}
          onEdit={onEdit}
          onDelete={onDelete}
          replyCount={post.replies.length}
          editing={editingId === post.id}
          renderEditor={renderEditor}
        >
          {replyingTo === post.id && renderReplyBox(post)}
          <ReplyList
            parentId={post.id}
            replies={post.replies}
            roster={roster}
            reveal={reveal}
            onEdit={onEdit}
            onDelete={onDelete}
            collapsed={threads.has(post.id)}
            onToggle={threads.toggle}
            editingId={editingId}
            renderEditor={renderEditor}
          />
        </PostCard>
      ))}
    </div>
  )
}
