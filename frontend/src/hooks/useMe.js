import { useEffect, useState } from 'react'
import { api } from '../lib/api'

/** Who this installation belongs to, the roster, and this member's colour. */
export function useMe() {
  const [me, setMe] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    api
      .me()
      .then((next) => live && setMe(next))
      .catch((caught) => live && setError(caught.message))
    return () => {
      live = false
    }
  }, [])

  return {
    member: me?.member ?? null,
    members: me?.members ?? [],
    readerIndex: me?.reader_index ?? null,
    loading: me === null && error === null,
    error,
  }
}
