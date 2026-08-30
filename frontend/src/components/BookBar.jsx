import { readerColourFor } from '../lib/readerColour'

const GROUPS = ['Currently Reading', 'Upcoming', 'Paused', 'Finished']

export function BookBar({
  book,
  books,
  onSelect,
  onAdd,
  onEdit,
  onRefresh,
  refreshing,
  member,
  members,
  viewer,
  onViewAs,
}) {
  return (
    <header className="bookbar">
      <div>
        <h1 className="bookbar__title display">{book?.title ?? 'Book Club'}</h1>
        {book?.author && <p className="bookbar__author muted">{book.author}</p>}

        <div className="bookbar__controls">
          <label className="sr-only" htmlFor="book-select">
            Choose a book
          </label>
          <select
            id="book-select"
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

          {book && (
            <button type="button" onClick={() => onEdit(book)}>
              Edit book
            </button>
          )}
          <button type="button" onClick={onRefresh} aria-live="polite">
            {refreshing ? 'Updating…' : 'Refresh'}
          </button>
        </div>
      </div>

      <div className="bookbar__right">
        <span style={{ color: readerColourFor(member, members), fontWeight: 600 }}>
          {member}
        </span>
        {members.length > 1 && (
          <span className="viewas muted">
            {/* A diagnostic, not a feature: it re-renders the page as the other
                member so blurring can be checked without editing .env. It never
                changes who posts are attributed to. */}
            <label htmlFor="view-as">View as</label>
            <select
              id="view-as"
              value={viewer}
              onChange={(event) => onViewAs(event.target.value)}
            >
              {members.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </span>
        )}
      </div>
    </header>
  )
}
