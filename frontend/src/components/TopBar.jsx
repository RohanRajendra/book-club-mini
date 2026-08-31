import { readerColourFor } from '../lib/readerColour'
import { ThemeToggle } from './ThemeToggle'

/**
 * Identity and session controls, and nothing about the book.
 *
 * It stays put while the page scrolls, so it holds only what is true
 * regardless of where you are: who you are, whose eyes you are borrowing, and
 * whether the lights are on.
 */
export function TopBar({
  member,
  members,
  viewer,
  onViewAs,
  onRefresh,
  refreshing,
  theme,
  onToggleTheme,
}) {
  const viewingAsOther = viewer && viewer !== member

  return (
    <header className="topbar">
      <span className="topbar__mark display">Book Club</span>

      <div className="topbar__right">
        {members.length > 1 && (
          // A diagnostic, not a feature: it re-renders the page as the other
          // member so blurring can be checked without editing .env. It never
          // changes who posts are attributed to.
          <label className="viewas">
            <span className="viewas__label muted">Viewing as</span>
            <select
              className={viewingAsOther ? 'viewas__select viewas__select--other' : 'viewas__select'}
              value={viewer}
              onChange={(event) => onViewAs(event.target.value)}
            >
              {members.map((name) => (
                <option key={name} value={name}>
                  {name === member ? `${name} (you)` : name}
                </option>
              ))}
            </select>
          </label>
        )}

        <span className="topbar__me" style={{ color: readerColourFor(member, members) }}>
          <span className="topbar__dot" aria-hidden="true" />
          {member}
        </span>

        <button
          type="button"
          className="iconbutton"
          onClick={onRefresh}
          title="Refresh"
          aria-live="polite"
        >
          <Refresh spinning={refreshing} />
          <span className="sr-only">{refreshing ? 'Updating' : 'Refresh'}</span>
        </button>

        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>
    </header>
  )
}

function Refresh({ spinning }) {
  return (
    <svg
      className={spinning ? 'spinning' : undefined}
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M13.6 6.8A5.8 5.8 0 1 0 13 10.5" />
      <path d="M13.9 2.8v4h-4" />
    </svg>
  )
}
