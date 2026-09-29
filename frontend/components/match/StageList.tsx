import type { StageItem, StageState } from '@/lib/matchProgress'

const STATE_TEXT: Record<StageState, string> = {
  done: 'done',
  current: 'in progress',
  pending: 'not started',
}

export function StageList({ items }: { items: StageItem[] }) {
  return (
    <ol className="space-y-2">
      {items.map((item) => (
        <li
          key={item.stage}
          aria-current={item.state === 'current' ? 'step' : undefined}
          className="flex items-center gap-3 text-sm"
        >
          <StageIcon state={item.state} />
          <span className={item.state === 'pending' ? 'text-muted' : undefined}>{item.label}</span>
          <span className="sr-only">({STATE_TEXT[item.state]})</span>
        </li>
      ))}
    </ol>
  )
}

// Mounted before any progress exists: a live region that appears together with its first
// message is often not announced.
export function Announcer({ text }: { text: string }) {
  return (
    <p aria-live="polite" className="sr-only">
      {text}
    </p>
  )
}

function StageIcon({ state }: { state: StageState }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className={`size-4 shrink-0 ${state === 'pending' ? 'text-subtle' : 'text-accent'}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="8" cy="8" r="6.25" />
      {state === 'done' ? <path d="M5 8.2l2 2 4-4.4" /> : null}
      {state === 'current' ? (
        <circle cx="8" cy="8" r="2.5" fill="currentColor" className="motion-safe:animate-pulse" />
      ) : null}
    </svg>
  )
}
