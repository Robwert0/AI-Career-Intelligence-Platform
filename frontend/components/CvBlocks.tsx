export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const id = title.replaceAll(' ', '-')
  return (
    <section aria-labelledby={id} className="space-y-5">
      <h2 id={id} className="font-mono text-xs tracking-widest text-accent uppercase">
        {title}
      </h2>
      {children}
    </section>
  )
}

export function Tags({ items }: { items: string[] }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li
          key={item}
          className="rounded-sm border border-line px-2 py-0.5 font-mono text-xs text-muted"
        >
          {item}
        </li>
      ))}
    </ul>
  )
}

export function Highlights({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed marker:text-line">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}

export function Chapter({
  id,
  index,
  title,
  intro,
  children,
}: {
  id: string
  index: string
  title: string
  intro?: string
  children: React.ReactNode
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="reveal space-y-8 sm:space-y-10">
      <header className="space-y-3">
        <p className="font-mono text-xs text-accent">
          {index} <span className="text-subtle">/ {id}</span>
        </p>
        <h2
          id={`${id}-title`}
          className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl"
        >
          {title}
        </h2>
        {intro ? <p className="max-w-2xl leading-relaxed text-muted">{intro}</p> : null}
      </header>
      {children}
    </section>
  )
}

export function Disclosure({
  summary,
  children,
  className = '',
}: {
  summary: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <details className={`group ${className}`}>
      <summary className="inline-flex cursor-pointer list-none items-center gap-2 rounded-sm py-1 text-sm font-medium text-accent hover:underline hover:underline-offset-4 [&::-webkit-details-marker]:hidden">
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
      <div className="pt-4">{children}</div>
    </details>
  )
}
