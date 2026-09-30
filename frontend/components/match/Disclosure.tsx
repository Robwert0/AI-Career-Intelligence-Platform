import { DISCLOSURE_SUMMARY } from './styles'

export function Disclosure({
  summary,
  children,
}: {
  summary: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <details className="group">
      <summary className={DISCLOSURE_SUMMARY}>
        <svg
          aria-hidden="true"
          viewBox="0 0 16 16"
          className="size-3.5 shrink-0 transition-transform group-open:rotate-90 motion-reduce:transition-none"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M6 3.5 10.5 8 6 12.5" />
        </svg>
        {summary}
      </summary>
      <div className="pt-3">{children}</div>
    </details>
  )
}
