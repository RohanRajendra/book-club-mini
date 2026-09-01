/**
 * Position validation, mirroring `application/position_rules.py`.
 *
 * The server enforces this; the client only says so sooner. The wording is
 * copied deliberately so a member sees the same sentence whichever side
 * catches it — if you change one, change the other.
 *
 * `inputMode="numeric"` on the field is a soft keyboard hint, not a
 * constraint: a paste or a hardware keyboard puts anything in there, and
 * `Number("abc")` is `NaN`, which serialises to `null` and reaches the server
 * as a missing chapter with a misleading error.
 */

const WHOLE_NUMBER = /^\d+$/

function problemWith(label, raw) {
  if (!WHOLE_NUMBER.test(raw)) return `A ${label} is a whole number.`
  if (Number(raw) < 1) return `A ${label} is 1 or more.`
  return null
}

export function positionProblem({ chapter = '', page = '' }, book) {
  const chapterRaw = chapter.trim()
  const pageRaw = page.trim()

  if (chapterRaw) {
    const problem = problemWith('chapter', chapterRaw)
    if (problem) return problem

    const total = book?.total_chapters
    if (total != null && Number(chapterRaw) > total) {
      return `${book.title} has ${total} chapters, so there is no chapter ${Number(chapterRaw)}.`
    }
  }

  if (pageRaw) {
    if (!chapterRaw) return 'A page needs a chapter to go with it.'
    const problem = problemWith('page', pageRaw)
    if (problem) return problem
  }

  return null
}
