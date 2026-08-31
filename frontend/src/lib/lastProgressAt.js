/**
 * When each member last said where they were.
 *
 * The feed carries positions but not when they were reached, and a spine tick
 * that is three weeks old should not read the same as one from this morning.
 * Only Progress posts count — a thought written at chapter nine is not a claim
 * to have arrived there.
 */
export function lastProgressAt(posts = []) {
  const latest = {}

  for (const post of posts) {
    if (post.type !== 'Progress') continue
    const at = Date.parse(post.created_at)
    if (Number.isNaN(at)) continue
    if (!(post.member in latest) || at > Date.parse(latest[post.member])) {
      latest[post.member] = post.created_at
    }
  }

  return latest
}
