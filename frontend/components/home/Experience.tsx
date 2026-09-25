import { Chapter, Highlights } from '@/components/CvBlocks'
import { cv } from '@/lib/cv'

export function Experience() {
  return (
    <Chapter id="experience" index="02" title="Experience">
      <ol className="relative space-y-12 border-l border-line pl-6 sm:pl-8">
        {cv.experience.map((role) => (
          <li key={`${role.company}|${role.period}`} className="relative">
            <span
              aria-hidden="true"
              className="absolute top-1.5 -left-[29px] size-2.5 rounded-full border-2 border-bg bg-accent sm:-left-[37px]"
            />
            <div className="grid gap-3 md:grid-cols-[11rem_minmax(0,1fr)] md:gap-8">
              <div className="space-y-1 font-mono text-xs text-muted">
                <p className="text-fg/80">{role.period}</p>
                <p>{role.location}</p>
              </div>
              <div className="space-y-3">
                <h3 className="text-lg font-medium tracking-tight">
                  {role.title}
                  <span className="block text-base font-normal text-muted">{role.company}</span>
                </h3>
                {role.context ? <p className="text-sm text-muted">{role.context}</p> : null}
                <Highlights items={role.highlights} />
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Chapter>
  )
}
