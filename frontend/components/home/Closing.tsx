import { Chapter } from '@/components/CvBlocks'
import { cv } from '@/lib/cv'

export function Education() {
  return (
    <Chapter id="education" index="05" title="Education">
      <div className="space-y-8">
        {cv.education.map((degree) => (
          <article
            key={degree.degree}
            className="grid gap-2 md:grid-cols-[11rem_minmax(0,1fr)] md:gap-8"
          >
            <p className="font-mono text-xs text-muted">{degree.period}</p>
            <div className="space-y-1.5">
              <h3 className="font-medium">{degree.degree}</h3>
              <p className="text-sm text-muted">{degree.school}</p>
              {degree.note ? <p className="text-sm leading-relaxed">{degree.note}</p> : null}
            </div>
          </article>
        ))}
        <div className="grid gap-2 md:grid-cols-[11rem_minmax(0,1fr)] md:gap-8">
          <p className="font-mono text-xs text-muted">languages</p>
          <p className="text-sm">{cv.languages.join(' · ')}</p>
        </div>
      </div>
    </Chapter>
  )
}

export function Contact() {
  const email = cv.links.find((link) => link.href.startsWith('mailto:'))
  const others = cv.links.filter((link) => link !== email)
  return (
    <section
      id="contact"
      aria-labelledby="contact-title"
      className="reveal rounded-lg border border-line bg-surface px-6 py-12 sm:px-12"
    >
      <p className="font-mono text-xs text-accent">
        06 <span className="text-muted">/ contact</span>
      </p>
      <h2 id="contact-title" className="mt-3 text-2xl font-medium tracking-tight sm:text-3xl">
        Let&apos;s talk.
      </h2>
      <p className="mt-3 max-w-xl leading-relaxed text-muted">
        Whether it is a role, a project, or a question about my work, email is the quickest way to
        reach me.
      </p>
      <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-4">
        {email ? (
          <a
            href={email.href}
            className="rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-on-accent transition-opacity hover:opacity-90"
          >
            {email.label}
          </a>
        ) : null}
        {others.map((link) => (
          <a
            key={link.href}
            href={link.href}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-xs text-muted underline decoration-line-strong underline-offset-4 hover:text-fg hover:decoration-accent"
          >
            {link.label} ↗
          </a>
        ))}
      </div>
    </section>
  )
}
