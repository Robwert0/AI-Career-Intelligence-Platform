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
    <section id={id} aria-labelledby={`${id}-title`} className="reveal space-y-10">
      <header className="space-y-3">
        <p className="font-mono text-xs text-accent">
          {index} <span className="text-subtle">/ {id}</span>
        </p>
        <h2 id={`${id}-title`} className="text-2xl font-medium tracking-tight sm:text-3xl">
          {title}
        </h2>
        {intro ? <p className="max-w-2xl leading-relaxed text-muted">{intro}</p> : null}
      </header>
      {children}
    </section>
  )
}
