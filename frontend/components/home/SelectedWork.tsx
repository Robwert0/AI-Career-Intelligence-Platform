import Link from 'next/link'
import { Chapter, Tags } from '@/components/CvBlocks'
import { cv } from '@/lib/cv'

export function SelectedWork() {
  return (
    <Chapter
      id="work"
      index="01"
      title="Selected engineering work"
      intro="What I built, the problem behind it, and what came of it. Work done for an employer is labelled as such."
    >
      <ol className="divide-y divide-line border-y border-line">
        {cv.selectedWork.map((work, position) => (
          <li
            key={work.title}
            className="grid gap-6 py-10 md:grid-cols-[13rem_minmax(0,1fr)] md:gap-10"
          >
            <div className="space-y-2">
              <p className="font-mono text-xs text-muted">
                {String(position + 1).padStart(2, '0')}
              </p>
              <p className="inline-block rounded-sm border border-line-strong px-2 py-0.5 font-mono text-[11px] text-accent">
                {work.context}
              </p>
              <p className="font-mono text-xs text-muted">{work.period}</p>
            </div>

            <div className="space-y-5">
              <h3 className="text-xl font-medium tracking-tight">{work.title}</h3>
              <dl className="grid gap-4 text-sm leading-relaxed sm:grid-cols-[7rem_minmax(0,1fr)] sm:gap-x-6">
                <dt className="font-mono text-xs text-muted sm:pt-0.5">problem</dt>
                <dd>{work.problem}</dd>
                <dt className="font-mono text-xs text-muted sm:pt-0.5">contribution</dt>
                <dd>{work.contribution}</dd>
                {work.outcome ? (
                  <>
                    <dt className="font-mono text-xs text-muted sm:pt-0.5">outcome</dt>
                    <dd>{work.outcome}</dd>
                  </>
                ) : null}
              </dl>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <Tags items={work.stack} />
                {work.projectSlug ? (
                  <Link
                    href={`/projects/${work.projectSlug}`}
                    className="font-mono text-xs text-accent underline underline-offset-4"
                  >
                    Project details<span className="sr-only">: {work.title}</span> →
                  </Link>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Chapter>
  )
}
