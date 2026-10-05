export type UserRole = 'recruiter' | 'hiring_manager' | 'engineer' | 'other'

export const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'recruiter', label: 'Recruiter' },
  { value: 'hiring_manager', label: 'Hiring manager' },
  { value: 'engineer', label: 'Engineer' },
  { value: 'other', label: 'Other' },
]

export function roleLabel(role: UserRole | null): string {
  return ROLE_OPTIONS.find((option) => option.value === role)?.label ?? '—'
}
