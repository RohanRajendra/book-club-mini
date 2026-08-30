import { escapes } from './QuickProgress'

const TYPES = ['Progress', 'Thought', 'Question']

/** Inline card at the top of the feed — not a modal, so the feed stays visible. */
export function Composer({ composer, onCancel, submitLabel = 'Post' }) {
  const { fields, setField, chooseType, submit, error, submitting, characterCount } =
    composer

  return (
    <form
      className="composer"
      onKeyDown={escapes(onCancel)}
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <div className="composer__types" role="group" aria-label="Post type">
        {TYPES.map((type) => (
          <button
            key={type}
            type="button"
            className="composer__type"
            aria-pressed={fields.type === type}
            onClick={() => chooseType(type)}
          >
            {type}
          </button>
        ))}
      </div>

      <div className="composer__row">
        <label className="sr-only" htmlFor="composer-chapter">
          Chapter
        </label>
        <input
          id="composer-chapter"
          inputMode="numeric"
          placeholder={fields.type === 'Progress' ? 'Chapter' : 'Chapter, optional'}
          value={fields.chapter}
          onChange={(event) => setField('chapter', event.target.value)}
        />
        <label className="sr-only" htmlFor="composer-page">
          Page, optional
        </label>
        <input
          id="composer-page"
          inputMode="numeric"
          placeholder="Page"
          value={fields.page}
          onChange={(event) => setField('page', event.target.value)}
        />
      </div>

      <label className="sr-only" htmlFor="composer-body">
        What are you thinking?
      </label>
      <textarea
        id="composer-body"
        placeholder={
          fields.type === 'Progress'
            ? 'Anything to add? Optional.'
            : 'What are you thinking?'
        }
        value={fields.body}
        onChange={(event) => setField('body', event.target.value)}
      />

      <div className="composer__footer">
        {characterCount && (
          <span className="mono muted">
            {characterCount.toLocaleString()} — longer posts are collapsed in the feed
          </span>
        )}
        {error && <span className="muted">{error}</span>}
        <span className="spacer" />
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? 'Posting…' : submitLabel}
        </button>
      </div>
    </form>
  )
}
