import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'

/**
 * Who this browser is, the roster, and this member's colour.
 *
 * Identity used to be a value in the server's configuration, so this hook only
 * ever had to read it. On a deployment both members share it is per-browser,
 * which means it can also be absent — hence `needsSignIn`, and the two actions
 * that change it.
 */
export function useMe() {
  const [me, setMe] = useState(null)
  const [error, setError] = useState(null)
  const [needsSignIn, setNeedsSignIn] = useState(false)

  const load = useCallback(async () => {
    try {
      setMe(await api.me())
      setNeedsSignIn(false)
      setError(null)
    } catch (caught) {
      // A 401 is not a failure to report. It is the app working correctly on a
      // browser that has not signed in yet, and the sign-in card is the answer.
      if (caught.status === 401) {
        setMe(null)
        setNeedsSignIn(true)
        setError(null)
      } else {
        setError(caught.message)
      }
    }
  }, [])

  useEffect(() => {
    let live = true
    load().then(() => live)
    return () => {
      live = false
    }
  }, [load])

  const signIn = useCallback(async ({ passphrase, member }) => {
    setMe(await api.signIn({ passphrase, member }))
    setNeedsSignIn(false)
    setError(null)
  }, [])

  const signOut = useCallback(async () => {
    await api.signOut()
    setMe(null)
    setNeedsSignIn(true)
  }, [])

  return {
    member: me?.member ?? null,
    members: me?.members ?? [],
    readerIndex: me?.reader_index ?? null,
    // False on an installation with no sign-in, where identity comes from
    // configuration and there is no session to end.
    signedIn: me?.signed_in ?? false,
    loading: me === null && error === null && !needsSignIn,
    needsSignIn,
    error,
    signIn,
    signOut,
  }
}
