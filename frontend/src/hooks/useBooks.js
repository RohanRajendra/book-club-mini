import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'

export const CURRENTLY_READING = 'Currently Reading'

/** The book list, the current selection, and add/update. */
export function useBooks() {
  const [books, setBooks] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const next = await api.books()
      setBooks(next)
      setError(null)
      // Default to whatever is Currently Reading, else the first book.
      setSelectedId((current) => {
        if (current && next.some((book) => book.id === current)) return current
        const reading = next.find((book) => book.status === CURRENTLY_READING)
        return reading?.id ?? next[0]?.id ?? null
      })
      return next
    } catch (caught) {
      setError(caught.message)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const addBook = useCallback(
    async (payload) => {
      const created = await api.addBook(payload)
      await load()
      setSelectedId(created.id)
      return created
    },
    [load],
  )

  const updateBook = useCallback(
    async (id, payload) => {
      const updated = await api.updateBook(id, payload)
      // Setting a book current pauses another one, so the whole list is stale.
      await load()
      return updated
    },
    [load],
  )

  return {
    books,
    selectedId,
    select: setSelectedId,
    book: books.find((item) => item.id === selectedId) ?? null,
    addBook,
    updateBook,
    refresh: load,
    loading,
    error,
  }
}
