/**
 * Reader colours are assigned by index into the roster so they stay stable.
 *
 * They are the app's primary wayfinding: name, initial, spine tick and reply
 * indent rule all share one hue, so scanning for "what did she say" needs no
 * reading. Both installations must list MEMBERS in the same order or the two
 * members swap colours between machines.
 */
export const READER_COLOURS = ['var(--reader-a)', 'var(--reader-b)']

export function assignReaderColour(index) {
  if (index == null || index < 0) return 'var(--muted)'
  return READER_COLOURS[index % READER_COLOURS.length]
}

export function readerColourFor(member, roster) {
  return assignReaderColour(roster ? roster.indexOf(member) : -1)
}

export function initialOf(member) {
  return member ? member.trim().charAt(0).toUpperCase() : '?'
}
