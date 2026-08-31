/**
 * The body is blurred and unselectable; author, position and timestamp stay
 * sharp on the card around it.
 *
 * Knowing that she said *something* at chapter 9 is not a spoiler, and hiding
 * the card entirely would hide that the club is active.
 */
export function BlurOverlay({ post, onReveal }) {
  return (
    <div className="blur">
      <div className="blur__body" aria-hidden="true">
        {post.body_preview}
      </div>
      <div className="blur__overlay">
        <span className="blur__label mono">
          Ahead of you{post.position ? ` — Chapter ${post.position.chapter}` : ''}
        </span>
        <button type="button" className="blur__reveal" onClick={() => onReveal(post.id)}>
          Read anyway
        </button>
      </div>
    </div>
  )
}
