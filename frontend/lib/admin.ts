import { authedRequest } from './api'
import type { ApiResult } from './http'
import type { UserRole } from './roles'

export const ADMIN_PAGE_SIZE = 50

export type AdminUserRow = {
  id: string
  email: string
  company: string | null
  role: UserRole | null
  created_at: string
  last_active_at: string | null
}

export type AdminUsersPage = {
  items: AdminUserRow[]
  total: number
  by_role: Record<UserRole | 'unspecified', number>
  limit: number
  offset: number
}

export function listUsers(offset: number): Promise<ApiResult<AdminUsersPage>> {
  return authedRequest<AdminUsersPage>(`/admin/users?limit=${ADMIN_PAGE_SIZE}&offset=${offset}`)
}

export function formatWhen(iso: string | null): string {
  if (iso === null) return 'never'
  return new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

// Offset paging over a newest-first list repeats a row whenever someone signs up between pages.
export function appendUnique(existing: AdminUserRow[], next: AdminUserRow[]): AdminUserRow[] {
  const seen = new Set(existing.map((row) => row.id))
  return [...existing, ...next.filter((row) => !seen.has(row.id))]
}
