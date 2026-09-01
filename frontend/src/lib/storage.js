/**
 * Preferences that survive a reload, without a crash when they can't.
 *
 * Private-mode Safari and some embedded webviews expose `localStorage` and then
 * throw on write; a disabled-storage browser throws on read. A theme choice is
 * not worth failing a render for, so both sides swallow the failure and the
 * preference simply lasts for the page load.
 */

const PREFIX = 'bookclub.'

export function readSetting(key, fallback = null) {
  try {
    const raw = window.localStorage.getItem(PREFIX + key)
    return raw === null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function writeSetting(key, value) {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}
