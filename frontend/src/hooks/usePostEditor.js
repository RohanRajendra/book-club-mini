import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { positionProblem } from '../lib/positionRules'

const asField = (value) => (value != null ? String(value) : '')

/**
 * Editing one post, in place.
 *
 * A long post is stored as a preview plus a separate body block, so the editor
 * cannot open on `body_preview`: saving that would silently truncate the post
 * to its own preview. Save stays disabled until the full body has arrived.
 */
export function usePostEditor(post, { book, onSave } = {}) {
  const [fields, setFields] = useState({
    body: post.body_preview,
    chapter: asField(post.position?.chapter),
    page: asField(post.position?.page),
  })
  const [loaded, setLoaded] = useState(!post.has_full_body)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!post.has_full_body) return undefined

    let live = true
    api
      .postBody(post.id)
      .then(({ body }) => {
        if (!live) return
        setFields((current) => ({ ...current, body }))
        setLoaded(true)
      })
      .catch((caught) => live && setError(caught.message))
    return () => {
      live = false
    }
  }, [post.id, post.has_full_body])

  const setField = useCallback((name, value) => {
    setFields((current) => {
      const next = { ...current, [name]: value }
      // Same rule as the composer: clearing the chapter clears the page, so
      // the page-without-a-chapter state cannot be reached at all.
      if (name === 'chapter' && !value.trim()) next.page = ''
      return next
    })
  }, [])

  const problem = positionProblem(fields, book)

  const save = useCallback(async () => {
    if (problem) {
      setError(problem)
      return false
    }

    setSaving(true)
    try {
      await onSave({
        body: fields.body,
        chapter: fields.chapter.trim() ? Number(fields.chapter) : null,
        page: fields.page.trim() ? Number(fields.page) : null,
      })
      return true
    } catch (caught) {
      // The edit stays on screen with its contents, as in the composer.
      setError(caught.message)
      return false
    } finally {
      setSaving(false)
    }
  }, [fields, onSave, problem])

  return {
    fields,
    setField,
    save,
    loaded,
    saving,
    error,
    canSave: loaded && !saving && problem === null,
  }
}
