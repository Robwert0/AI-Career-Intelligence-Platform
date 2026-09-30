import { Chapter, Disclosure, Highlights } from '@/components/CvBlocks'
import { cv, type Role } from '@/lib/cv'

function RoleBody({ role }: { role: Role }) {
  if (!role.keyHighlights) {
    return (
      <ul className="list-disc space-y-1.5 pl-5 leading-relaxed text-muted marker:text-line-strong">
        {role.highlights.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    )
  }
  return (
    <div className="space-y-5">
      <ul className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
        {role.keyHighlights.map((item) => (
          <li key={item.lead} className="space-y-1 border-t border-line pt-3">
            <p className="font-medium">{item.lead}</p>
            <p className="leading-relaxed text-muted">{item.text}</p>
          </li>
        ))}
      </ul>
      <Disclosure
        summary={
          <>
            All responsibilities ({role.highlights.length})
            <span className="sr-only">
              : {role.title}, {role.company}
            </span>
          </>
        }
      >
        <Highlights items={role.highlights} />
      </Disclosure>
    </div>
  )
}

export function Experience() {
  return (
    <Chapter id="experience" index="02" title="Experience">
      <ol className="space-y-12">
        {cv.experience.map((role) => (
          <li
            key={`${role.company}|${role.period}`}
            className="grid gap-3 md:grid-cols-[11rem_minmax(0,1fr)] md:gap-8"
          >
            <div className="space-y-1 font-mono text-xs text-subtle md:pt-1.5">
              <p className="text-muted">{role.period}</p>
              <p>{role.location}</p>
            </div>
            <div className="space-y-4">
              <div className="space-y-1">
                <h3 className="text-xl font-semibold tracking-tight">{role.title}</h3>
                <p className="text-muted">{role.company}</p>
              </div>
              {role.context ? <p className="text-sm text-subtle">{role.context}</p> : null}
              <RoleBody role={role} />
            </div>
          </li>
        ))}
      </ol>
    </Chapter>
  )
}
