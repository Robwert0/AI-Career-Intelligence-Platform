import Link from 'next/link'
import { Chapter, Disclosure, Tags } from '@/components/CvBlocks'
import { ChatPipeline } from '@/components/home/ChatPipeline'
import { cv, type SelectedWork as Work } from '@/lib/cv'
import type { Project } from '@/lib/projects'

const LABEL = 'font-mono text-xs text-subtle'

function Attribution({ work }: { work: Work }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-xs">
      {work.employer ? (
        <span className="rounded-sm border border-accent/50 px-2 py-0.5 text-accent">
          {work.employer}
        </span>
      ) : null}
      <span className="text-muted">{work.context}</span>
      <span className="whitespace-nowrap text-subtle">
        <span aria-hidden="true" className="mr-2 text-line-strong">
          ·
        </span>
        {work.period}
      </span>
    </p>
  )
}

function Details({ work }: { work: Work }) {
  return (
    <Disclosure
      summary={
        <>
          Problem, my part and decisions<span className="sr-only">: {work.title}</span>
        </>
      }
    >
      <dl className="grid gap-x-6 gap-y-3 leading-relaxed sm:grid-cols-[6.5rem_minmax(0,1fr)]">
        <dt className={`${LABEL} sm:pt-1`}>problem</dt>
        <dd>{work.problem}</dd>
        <dt className={`${LABEL} sm:pt-1`}>my part</dt>
        <dd>{work.contribution}</dd>
        <dt className={`${LABEL} sm:pt-1`}>decisions</dt>
        <dd>
          <ul className="list-disc space-y-1.5 pl-4 marker:text-line-strong">
            {work.decisions.map((decision) => (
              <li key={decision}>{decision}</li>
            ))}
          </ul>
        </dd>
      </dl>
    </Disclosure>
  )
}

function WorkPreview({ work, lead = false }: { work: Work; lead?: boolean }) {
  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <Attribution work={work} />
        <h3
          className={`font-semibold tracking-tight ${lead ? 'text-2xl sm:text-3xl' : 'text-xl sm:text-2xl'}`}
        >
          {work.title}
        </h3>
        <p className="max-w-2xl leading-relaxed text-muted">{work.summary}</p>
      </div>
      <p className="max-w-2xl border-l-2 border-accent pl-4 leading-relaxed">{work.highlight}</p>
      <Tags items={work.stack} />
      <div className="space-y-2">
        {work.projectSlug ? (
          <Link
            href={`/projects/${work.projectSlug}`}
            className="inline-block rounded-sm py-1 text-sm font-medium text-accent underline underline-offset-4 hover:decoration-2"
          >
            Project details<span className="sr-only">: {work.title}</span> →
          </Link>
        ) : null}
        <Details work={work} />
      </div>
    </div>
  )
}

function ProjectList({ items }: { items: Project[] }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {items.map((project) => (
        <li key={project.slug}>
          <Link
            href={`/projects/${project.slug}`}
            className="group grid gap-1 py-3.5 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_1rem] sm:items-baseline sm:gap-6"
          >
            <span className="font-medium transition-colors group-hover:text-accent">
              {project.name}
            </span>
            <span className="text-sm text-muted">
              {project.tagline}
              <span className="text-subtle"> · {project.context}</span>
            </span>
            <span
              aria-hidden="true"
              className="hidden text-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-accent motion-reduce:transition-none sm:block"
            >
              →
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

export function SelectedWork() {
  const lead = cv.selectedWork.find((work) => work.lead)
  const others = cv.selectedWork.filter((work) => !work.lead)
  const featured = new Set(cv.selectedWork.map((work) => work.projectSlug))
  const remaining = cv.projects.filter((project) => !featured.has(project.slug))
  const more = remaining.filter((project) => project.category !== 'learning')
  const learning = remaining.filter((project) => project.category === 'learning')

  return (
    <Chapter
      id="work"
      index="01"
      title="Featured work"
      intro="The systems I’d point to first. Employer work is marked with the company’s name."
    >
      <div className="space-y-6">
        {lead ? (
          <article className="space-y-8 rounded-xl border border-line bg-surface p-5 sm:p-8">
            <WorkPreview work={lead} lead />
            <ChatPipeline />
          </article>
        ) : null}

        <div className="grid gap-6 md:grid-cols-2">
          {others.map((work) => (
            <article key={work.title} className="rounded-xl border border-line p-5 sm:p-8">
              <WorkPreview work={work} />
            </article>
          ))}
        </div>
      </div>

      <div id="projects" className="space-y-3">
        <h3 className="text-xl font-semibold tracking-tight">More projects</h3>
        <div className="grid gap-4 lg:grid-cols-2 lg:gap-8">
          <Disclosure summary={`Internship, thesis and challenge projects (${more.length})`}>
            <ProjectList items={more} />
          </Disclosure>
          <Disclosure summary={`Earlier and learning projects (${learning.length})`}>
            <ProjectList items={learning} />
          </Disclosure>
        </div>
      </div>
    </Chapter>
  )
}
