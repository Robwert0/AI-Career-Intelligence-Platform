function plural(count: number, unit: string): string {
  return `${count} ${unit}${count === 1 ? '' : 's'}`
}

export function formatWait(seconds: number): string {
  if (seconds <= 0) return 'a moment'
  if (seconds < 60) return plural(seconds, 'second')
  if (seconds < 3600) return plural(Math.ceil(seconds / 60), 'minute')
  return plural(Math.ceil(seconds / 3600), 'hour')
}
