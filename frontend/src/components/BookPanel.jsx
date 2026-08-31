const GROUPS = ['Currently Reading', 'Upcoming', 'Paused', 'Finished']

/**
 * The book, in the left rail.
 *
 * The title is the largest thing on the page and it lives beside the feed
 * rather than above it: scrolling should never cost you the answer to "which
 * book is this".
 */
export function BookPanel({ book, books, onSelect, onAdd, onEdit }) {
  return (
    <div className="bookpanel">
      {book ? (
        <>
          <h3 className="bookpanel__title display">{book.title}</h3>
          {book.author && <p className="bookpanel__author muted">{book.author}</p>}
          <dl className="bookpanel__meta mono muted">
            <div>
              <dt>Status</dt>
              <dd>{book.status}</dd>
            </div>
            <div>
              <dt>Chapters</dt>
              <dd>{book.total_chapters ?? '—'}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="muted">No book selected.</p>
      )}

      <label className="sr-only" htmlFor="book-select">
        Choose a book
      </label>
      <select
        id="book-select"
        className="bookpanel__select"
        value={book?.id ?? ''}
        onChange={(event) =>
          event.target.value === '__add' ? onAdd() : onSelect(event.target.value)
        }
      >
        {GROUPS.map((group) => {
          const inGroup = books.filter((item) => item.status === group)
          if (!inGroup.length) return null
          return (
            <optgroup key={group} label={group}>
              {inGroup.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </optgroup>
          )
        })}
        <option value="__add">＋ Add book</option>
      </select>

      <div className="bookpanel__actions">
        {book && (
          // "Edit" alone collides with the Edit on every post card, which is
          // the same word for a different object.
          <button type="button" onClick={() => onEdit(book)}>
            Edit<span className="sr-only"> book</span>
          </button>
        )}
        <button type="button" onClick={onAdd}>
          Add book
        </button>
      </div>
    </div>
  )
}
