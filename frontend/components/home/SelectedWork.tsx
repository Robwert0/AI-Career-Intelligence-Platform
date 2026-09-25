import Link from 'next/link'
import { Chapter, Tags } from '@/components/CvBlocks'
import { cv, type SelectedWork as Work } from '@/lib/cv'

const LABEL = 'font-mono text-xs text-subtle'

function Attribution({ work }: { work: Work }) {
  return (
    <p className="inline-flex flex-wrap items-center gap-2 font-mono text-[11px]">
      {work.employer ? (
        <span className="rounded-sm border border-accent/50 px-2 py-0.5 text-accent">
          {work.employer}
        </span>
      ) : null}
      <span className="text-subtle">{work.context}</span>
    </p>
  )
}

function WorkEntry({ work, position }: { work: Work; position: number }) {
  return (
    <li className="grid gap-5 py-10 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-10">
      <div className="space-y-2">
        <p className={LABEL}>{String(position).padStart(2, '0')}</p>
        <Attribution work={work} />
        <p className={LABEL}>{work.period}</p>
      </div>

      <div className="space-y-5">
        <div className="space-y-2">
          <h3 className="text-xl font-medium tracking-tight">{work.title}</h3>
          <p className="leading-relaxed text-muted">{work.summary}</p>
        </div>
        <dl className="grid gap-x-6 gap-y-4 text-sm leading-relaxed sm:grid-cols-[8rem_minmax(0,1fr)]">
          <dt className={`${LABEL} sm:pt-0.5`}>problem</dt>
          <dd>{work.problem}</dd>
          <dt className={`${LABEL} sm:pt-0.5`}>my part</dt>
          <dd>{work.contribution}</dd>
          <dt className={`${LABEL} sm:pt-0.5`}>decisions</dt>
          <dd>
            <ul className="list-disc space-y-1.5 pl-4 marker:text-line-strong">
              {work.decisions.map((decision) => (
                <li key={decision}>{decision}</li>
              ))}
            </ul>
          </dd>
          {work.outcome ? (
            <>
              <dt className={`${LABEL} sm:pt-0.5`}>result</dt>
              <dd>{work.outcome}</dd>
            </>
          ) : null}
        </dl>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Tags items={work.stack} />
          {work.projectSlug ? (
            <Link
              href={`/projects/${work.projectSlug}`}
              className="rounded-sm font-mono text-xs text-accent underline underline-offset-4 hover:decoration-2"
            >
              Project details<span className="sr-only">: {work.title}</span> →
            </Link>
          ) : null}
        </div>
      </div>
    </li>
  )
}

export function SelectedWork() {
  const featured = new Set(cv.selectedWork.map((work) => work.projectSlug))
  const more = cv.projects.filter((project) => !featured.has(project.slug))

  return (
    <Chapter
      id="work"
      index="01"
      title="Selected work"
      intro="Selected systems and features I’ve built, with the technical decisions behind them."
    >
      <ol className="divide-y divide-line border-y border-line">
        {cv.selectedWork.map((work, index) => (
          <WorkEntry key={work.title} work={work} position={index + 1} />
        ))}
      </ol>

      <div id="projects" className="space-y-4 pt-4">
        <h3 className="text-lg font-medium tracking-tight">More projects</h3>
        <p className="text-sm text-muted">
          University work, courses and practice projects from my GitHub, each with its own page.
        </p>
        <ul className="divide-y divide-line border-y border-line">
          {more.map((project) => (
            <li key={project.slug}>
              <Link
                href={`/projects/${project.slug}`}
                className="group grid gap-1 py-4 sm:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_1rem] sm:items-baseline sm:gap-6"
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
                  className="hidden text-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-accent sm:block"
                >
                  →
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </Chapter>
  )
}
