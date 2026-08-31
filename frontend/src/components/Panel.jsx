import { Chevron } from './Chevron'

/**
 * A collapsible rail section.
 *
 * The heading is the control — the whole strip is clickable — and
 * `aria-expanded` on it is what a screen reader announces. `hidden` rather
 * than a stylesheet rule keeps the collapsed contents out of the tab order
 * without a second mechanism to remember.
 */
export function Panel({ id, title, badge, open, onToggle, children }) {
  return (
    <section className={open ? 'panel' : 'panel panel--closed'}>
      <h2 className="panel__head">
        <button
          type="button"
          className="panel__toggle"
          aria-expanded={open}
          aria-controls={`panel-${id}`}
          onClick={() => onToggle(id)}
        >
          <Chevron className="chevron panel__chevron" />
          <span className="panel__title">{title}</span>
          {badge != null && <span className="panel__badge mono">{badge}</span>}
        </button>
      </h2>
      <div id={`panel-${id}`} className="panel__body" hidden={!open}>
        {children}
      </div>
    </section>
  )
}
