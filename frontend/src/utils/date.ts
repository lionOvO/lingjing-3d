/**
 * Format timestamps returned by the API.
 *
 * The MySQL TIMESTAMP columns are stored and returned as UTC values without
 * an offset. Appending `Z` before parsing prevents the browser from treating
 * that value as local time and displaying it several hours too early.
 */
export function formatApiDate(value?: string | null): string {
  if (!value) return '暂无记录'

  const raw = value.trim()
  if (!raw) return '暂无记录'

  // A date-only value has no time-zone meaning and should remain local.
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(raw)
  let normalized = dateOnly ? `${raw}T00:00:00` : raw.replace(' ', 'T')

  if (!dateOnly && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)) {
    normalized += 'Z'
  }

  // JavaScript Date supports millisecond precision; trim longer fractions
  // emitted by some database drivers before parsing.
  normalized = normalized.replace(/\.(\d{3})\d+(?=(?:Z|[+-]\d{2}:?\d{2})?$)/, '.$1')

  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) return value

  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}
