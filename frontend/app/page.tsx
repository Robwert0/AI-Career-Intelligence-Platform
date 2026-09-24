import Image from 'next/image'
import { cv, type Project, type Role } from '@/lib/cv'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={title} className="space-y-5">
      <h2 id={title} className="font-mono text-xs tracking-widest text-accent uppercase">
        {title}
      </h2>
      {children}
    </section>
  )
}

function Portrait() {
  const frame = 'size-28 shrink-0 rounded-full border border-line sm:size-32'

  if (!cv.photo) {
    return (
      <div aria-hidden="true" className={`${frame} flex items-center justify-center bg-line`}>
        <span className="font-mono text-3xl text-muted">{cv.initials}</span>
      </div>
    )
  }
  return (
    <Image
      src={cv.photo.src}
      alt={cv.photo.alt}
      width={256}
      height={256}
      loading="eager"
      className={`${frame} object-cover`}
    />
  )
}

function Tags({ items }: { items: string[] }) {
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

function Highlights({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed marker:text-line">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}

function RoleEntry({ role }: { role: Role }) {
  return (
    <article className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <h3 className="font-medium">
          {role.title} <span className="text-muted">· {role.company}</span>
        </h3>
        <span className="font-mono text-xs text-muted">
          {role.period} · {role.location}
        </span>
      </div>
      {role.context ? <p className="text-sm text-muted">{role.context}</p> : null}
      <Highlights items={role.highlights} />
    </article>
  )
}

function ProjectCard({ project }: { project: Project }) {
  return (
    <article className="flex flex-col gap-3 rounded-sm border border-line p-5 md:last:odd:col-span-2">
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="font-medium">{project.name}</h3>
        <span className="font-mono text-xs text-muted">{project.period}</span>
      </div>
      <p className="text-sm text-muted">{project.tagline}</p>
      <Highlights items={project.highlights} />
      <div className="mt-auto space-y-3 pt-2">
        <Tags items={project.stack} />
        {project.repo ? (
          <a
            href={project.repo}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block font-mono text-xs text-accent underline underline-offset-4"
          >
            source ↗
          </a>
        ) : null}
      </div>
    </article>
  )
}

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 space-y-14 px-4 pt-16 pb-32">
      <header className="flex flex-col gap-6 sm:flex-row sm:items-center">
        <Portrait />
        <div className="space-y-2">
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{cv.name}</h1>
          <p className="text-lg text-muted">{cv.title}</p>
          <p className="font-mono text-xs text-muted">{cv.location}</p>
          <ul className="flex flex-wrap gap-x-4 gap-y-1 pt-1 font-mono text-xs">
            {cv.links.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  {...(link.href.startsWith('https:')
                    ? { target: '_blank', rel: 'noopener noreferrer' }
                    : {})}
                  className="text-accent underline underline-offset-4"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </header>

      <Section title="summary">
        <p className="max-w-prose leading-relaxed">{cv.summary}</p>
      </Section>

      <Section title="experience">
        <div className="space-y-8">
          {cv.experience.map((role) => (
            <RoleEntry key={`${role.company}|${role.period}`} role={role} />
          ))}
        </div>
      </Section>

      <Section title="projects">
        <div className="grid gap-4 md:grid-cols-2">
          {cv.projects.map((project) => (
            <ProjectCard key={project.name} project={project} />
          ))}
        </div>
      </Section>

      <Section title="skills">
        <dl className="space-y-4">
          {cv.skills.map((group) => (
            <div key={group.name} className="grid gap-2 sm:grid-cols-[9rem_1fr]">
              <dt className="text-sm text-muted">{group.name}</dt>
              <dd>
                <Tags items={group.skills} />
              </dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="education">
        <div className="space-y-6">
          {cv.education.map((degree) => (
            <article key={degree.degree} className="space-y-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                <h3 className="font-medium">{degree.degree}</h3>
                <span className="font-mono text-xs text-muted">{degree.period}</span>
              </div>
              <p className="text-sm text-muted">{degree.school}</p>
              {degree.note ? <p className="text-sm leading-relaxed">{degree.note}</p> : null}
            </article>
          ))}
        </div>
      </Section>

      <Section title="languages">
        <p className="text-sm">{cv.languages.join(' · ')}</p>
      </Section>
    </main>
  )
}
