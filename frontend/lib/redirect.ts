export const DEFAULT_AFTER_SIGN_IN = '/chat'

// An exact allowlist, never a prefix check: any open `next` is an open redirect.
const ALLOWED_NEXT = new Set(['/chat', '/match'])

export function safeNextPath(raw: string | null): string {
  return raw !== null && ALLOWED_NEXT.has(raw) ? raw : DEFAULT_AFTER_SIGN_IN
}

export function withNext(path: string, next: string): string {
  if (next === DEFAULT_AFTER_SIGN_IN) return path
  const separator = path.includes('?') ? '&' : '?'
  return `${path}${separator}next=${encodeURIComponent(next)}`
}
