import { useCallback, useMemo, useState } from 'react'
import { positionProblem } from '../lib/positionRules'

export const COUNT_THRESHOLD = 1700
export const PREVIEW_LIMIT = 1900

const EMPTY = { type: 'Progress', chapter: '', page: '', body: '' }

/**
 * The composer: type, fields, prefill, validation, submit.
 *
 * Position pre-filling lives here rather than in the backend use case: putting
 * the default server-side would make it impossible for a member to
 * deliberately post without a position.
 */
export function useComposer({ viewerPosition, book, onSubmit } = {}) {
  const [open, setOpen] = useState(false)
  const [fields, setFields] = useState(EMPTY)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const prefill = useCallback(
    (type) => {
      // Progress states where you are, so it never pre-fills. Thought and
      // Question default to your current position, editable and clearable.
      if (type === 'Progress') return { chapter: '', page: '' }
      return {
        chapter: viewerPosition?.chapter != null ? String(viewerPosition.chapter) : '',
        page: viewerPosition?.page != null ? String(viewerPosition.page) : '',
      }
    },
    [viewerPosition],
  )

  const chooseType = useCallback(
    (type) => setFields((current) => ({ ...current, type, ...prefill(type) })),
    [prefill],
  )

  const setField = useCallback((name, value) => {
    setFields((current) => {
      const next = { ...current, [name]: value }
      // Clearing the chapter clears the page with it. A prefilled position is
      // clearable and the app does not warn about the result, so the
      // page-needs-a-chapter state is made unreachable rather than reported
      // back as an error the member has to fix.
      if (name === 'chapter' && !value.trim()) next.page = ''
      return next
    })
  }, [])

  const validate = useCallback(
    (values) => {
      if (values.type === 'Progress' && !values.chapter.trim()) {
        return 'Progress needs a chapter number.'
      }
      if (values.type !== 'Progress' && !values.body.trim()) {
        return 'Write something first.'
      }
      return positionProblem(values, book)
    },
    [book],
  )

  const submit = useCallback(async () => {
    const problem = validate(fields)
    if (problem) {
      setError(problem)
      return null
    }

    setSubmitting(true)
    try {
      const created = await onSubmit({
        type: fields.type,
        body: fields.body,
        chapter: fields.chapter.trim() ? Number(fields.chapter) : null,
        page: fields.page.trim() ? Number(fields.page) : null,
      })
      setFields(EMPTY)
      setError(null)
      setOpen(false)
      return created
    } catch (caught) {
      // Keeping the contents on failure is the difference between an annoying
      // app and one that loses your writing.
      setError(caught.message)
      return null
    } finally {
      setSubmitting(false)
    }
  }, [fields, onSubmit, validate])

  const cancel = useCallback(() => {
    // Contents survive collapse within the session.
    setOpen(false)
    setError(null)
  }, [])

  const characterCount = useMemo(
    () => (fields.body.length > COUNT_THRESHOLD ? fields.body.length : null),
    [fields.body],
  )

  return {
    open,
    setOpen,
    fields,
    setField,
    chooseType,
    submit,
    cancel,
    error,
    submitting,
    characterCount,
    willCollapse: fields.body.length > PREVIEW_LIMIT,
    isValid: validate(fields) === null,
  }
}
