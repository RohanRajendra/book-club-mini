import { useState } from 'react'

/**
 * The one gate in front of a deployment both members reach.
 *
 * The name is typed rather than chosen from a list, because the list would
 * have to be served to anyone who finds the URL. Two first names is a small
 * thing to leak and a free one to avoid, and each member types theirs about
 * once a quarter.
 */
export function SignIn({ onSignIn }) {
  const [passphrase, setPassphrase] = useState('')
  const [member, setMember] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSignIn({ passphrase, member: member.trim() })
    } catch (caught) {
      setError(caught.message)
      setPassphrase('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="signin">
      <form className="signin__card" onSubmit={handleSubmit}>
        <h1 className="signin__title">Book Club</h1>

        <label className="signin__field">
          Passphrase
          <input
            autoFocus
            type="password"
            autoComplete="current-password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
          />
        </label>

        <label className="signin__field">
          Who's reading?
          <input
            type="text"
            autoComplete="username"
            autoCapitalize="words"
            value={member}
            onChange={(event) => setMember(event.target.value)}
          />
        </label>

        {error ? <p className="signin__error">{error}</p> : null}

        <button
          type="submit"
          className="primary"
          disabled={busy || !passphrase || !member.trim()}
        >
          {busy ? 'Checking…' : 'Continue'}
        </button>

        <p className="signin__note">Stays signed in on this device.</p>
      </form>
    </div>
  )
}
