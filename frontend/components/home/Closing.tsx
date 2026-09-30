import { Chapter } from '@/components/CvBlocks'
import { LinkIcon } from '@/components/LinkIcon'
import { cv } from '@/lib/cv'

export function Education() {
  return (
    <Chapter id="education" index="04" title="Education">
      <div className="space-y-8">
        {cv.education.map((degree) => (
          <article
            key={degree.degree}
            className="grid gap-2 md:grid-cols-[11rem_minmax(0,1fr)] md:gap-8"
          >
            <p className="font-mono text-xs text-subtle md:pt-1">{degree.period}</p>
            <div className="space-y-1.5">
              <h3 className="text-lg font-semibold tracking-tight">{degree.degree}</h3>
              <p className="text-muted">{degree.school}</p>
              {degree.note ? <p className="leading-relaxed text-muted">{degree.note}</p> : null}
            </div>
          </article>
        ))}
        <div className="grid gap-2 md:grid-cols-[11rem_minmax(0,1fr)] md:gap-8">
          <p className="font-mono text-xs text-subtle">languages</p>
          <p>{cv.languages.join(' · ')}</p>
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
      className="reveal rounded-xl border border-line bg-surface px-5 py-10 sm:px-12 sm:py-12"
    >
      <p className="font-mono text-xs text-accent">
        05 <span className="text-subtle">/ contact</span>
      </p>
      <h2 id="contact-title" className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
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
            className="inline-flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted transition-colors hover:bg-bg hover:text-fg"
          >
            <LinkIcon name={link.name} />
            {link.name}
          </a>
        ))}
      </div>
    </section>
  )
}
