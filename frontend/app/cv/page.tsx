import type { Metadata } from 'next'
import { Highlights, Section, Tags } from '@/components/CvBlocks'
import { PrintButton } from '@/components/PrintButton'
import { SiteNav } from '@/components/SiteNav'
import { cv } from '@/lib/cv'

export const metadata: Metadata = {
  title: 'CV — Robert Mirea',
  description: `${cv.name}, ${cv.title}: experience, projects, skills and education.`,
}

const actionClass =
  'rounded-md border border-line-strong px-3.5 py-2 text-sm transition-colors hover:border-accent hover:text-accent'

export default function CvPage() {
  const cvProjects = cv.projects.filter((project) => project.category !== 'learning')
  return (
    <>
      <SiteNav initials={cv.initials} />
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-12 px-6 pt-12 pb-24 sm:px-10 print:max-w-none print:space-y-7 print:p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
          <p className="font-mono text-xs text-muted">curriculum vitae</p>
          <div className="flex flex-wrap gap-2">
            {cv.pdf ? (
              <a href={cv.pdf.href} download className={actionClass}>
                Download PDF
              </a>
            ) : null}
            <PrintButton className={actionClass} />
          </div>
        </div>

        <header className="space-y-3 border-b border-line pb-8 print:pb-5">
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{cv.name}</h1>
          <p className="text-lg text-muted">
            {cv.title} · {cv.location}
          </p>
          <ul className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs">
            {cv.links.map((link) => (
              <li key={link.href}>
                <a href={link.href} className="text-accent underline underline-offset-4">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </header>

        <Section title="summary">
          <p className="leading-relaxed">{cv.summary}</p>
        </Section>

        <Section title="experience">
          <div className="space-y-8 print:space-y-5">
            {cv.experience.map((role) => (
              <article
                key={`${role.company}|${role.period}`}
                className="space-y-2 break-inside-avoid"
              >
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
            ))}
          </div>
        </Section>

        <Section title="projects">
          <div className="space-y-6 print:space-y-4">
            {cvProjects.map((project) => (
              <article key={project.slug} className="space-y-1.5 break-inside-avoid">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                  <h3 className="font-medium">
                    {project.name} <span className="text-muted">· {project.context}</span>
                  </h3>
                  <span className="font-mono text-xs text-muted">{project.period}</span>
                </div>
                <p className="text-sm leading-relaxed">{project.purpose}</p>
                <p className="font-mono text-xs text-muted">{project.stack.join(' · ')}</p>
              </article>
            ))}
          </div>
        </Section>

        <Section title="skills">
          <dl className="space-y-3">
            {cv.skills.map((group) => (
              <div key={group.name} className="grid gap-2 sm:grid-cols-[11rem_1fr]">
                <dt className="text-sm text-muted">{group.name}</dt>
                <dd>
                  <Tags items={group.skills} />
                </dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section title="education">
          <div className="space-y-5">
            {cv.education.map((degree) => (
              <article key={degree.degree} className="space-y-1 break-inside-avoid">
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
    </>
  )
}
