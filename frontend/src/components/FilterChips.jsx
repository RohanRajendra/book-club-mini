const CHIPS = [
  ['all', 'All'],
  ['progress', 'Progress'],
  ['thought', 'Thoughts'],
  ['question', 'Questions'],
]

/** Counts come from the API for every chip, so filtering costs no request. */
export function FilterChips({ filter, setFilter, counts }) {
  return (
    <div className="chips" role="group" aria-label="Filter posts">
      {CHIPS.map(([key, label]) => (
        <button
          key={key}
          type="button"
          className="chip"
          aria-pressed={filter === key}
          onClick={() => setFilter(key)}
        >
          <span className="chip__label">{label}</span>
          <span className="chip__count mono">{counts[key] ?? 0}</span>
        </button>
      ))}
    </div>
  )
}
