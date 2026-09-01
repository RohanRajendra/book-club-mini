/**
 * Light and dark.
 *
 * The icon shows what a click will *give* you, not the state you are in — the
 * state is the whole page, and nobody needs a badge for it.
 */
export function ThemeToggle({ theme, onToggle }) {
  const dark = theme === 'dark'
  const label = dark ? 'Switch to light theme' : 'Switch to dark theme'

  return (
    <button type="button" className="iconbutton" onClick={onToggle} title={label}>
      {dark ? <Sun /> : <Moon />}
      <span className="sr-only">{label}</span>
    </button>
  )
}

const icon = {
  viewBox: '0 0 16 16',
  width: 16,
  height: 16,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.4,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  focusable: 'false',
}

function Sun() {
  return (
    <svg {...icon}>
      <circle cx="8" cy="8" r="3.1" />
      <path d="M8 1v1.6M8 13.4V15M1 8h1.6M13.4 8H15M3.05 3.05l1.13 1.13M11.82 11.82l1.13 1.13M12.95 3.05l-1.13 1.13M4.18 11.82l-1.13 1.13" />
    </svg>
  )
}

function Moon() {
  return (
    <svg {...icon}>
      <path d="M13.5 9.6A5.9 5.9 0 0 1 6.4 2.5a5.9 5.9 0 1 0 7.1 7.1Z" />
    </svg>
  )
}
