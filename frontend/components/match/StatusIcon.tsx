import type { RequirementStatus } from '@/lib/match'

const COLOR: Record<RequirementStatus, string> = {
  demonstrated: 'text-accent',
  partial: 'text-fg',
  not_demonstrated: 'text-muted',
  unmet: 'text-danger',
  not_assessed: 'text-subtle',
}

export function StatusIcon({ status }: { status: RequirementStatus }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className={`size-4 shrink-0 ${COLOR[status]}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle
        cx="8"
        cy="8"
        r="6.25"
        strokeDasharray={status === 'not_assessed' ? '2 2' : undefined}
      />
      {status === 'demonstrated' ? <path d="M5 8.2l2 2 4-4.4" /> : null}
      {status === 'partial' ? (
        <path d="M8 1.75a6.25 6.25 0 0 1 0 12.5z" fill="currentColor" />
      ) : null}
      {status === 'unmet' ? <path d="M5.75 5.75l4.5 4.5M10.25 5.75l-4.5 4.5" /> : null}
      {status === 'not_assessed' ? <path d="M5.5 8h5" /> : null}
    </svg>
  )
}
