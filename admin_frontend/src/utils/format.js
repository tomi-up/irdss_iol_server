// Display formatters shared across the admin tables.

// Formats an ISO timestamp for table display, tolerating nulls from optional fields.
export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// Renders a duration in seconds as a compact "2d 4h 13m" style uptime string.
export function formatUptime(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  const total = Math.floor(seconds)
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60

  if (days) return `${days}d ${hours}h ${minutes}m`
  if (hours) return `${hours}h ${minutes}m`
  if (minutes) return `${minutes}m ${secs}s`
  return `${secs}s`
}

// Colours a request duration so slow endpoints stand out in the log table.
export function latencyToneClass(ms) {
  if (ms >= 1000) return 'text-rose-600'
  if (ms >= 300) return 'text-amber-600'
  return 'text-slate-500'
}

// Maps an HTTP status code onto a badge tone.
export function statusCodeTone(code) {
  if (code >= 500) return 'red'
  if (code >= 400) return 'amber'
  return 'green'
}
