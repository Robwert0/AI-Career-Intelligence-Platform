import { Chapter } from '@/components/CvBlocks'
import { cv } from '@/lib/cv'

export function Skills() {
  return (
    <Chapter id="skills" index="03" title="Technical skills">
      <dl className="grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
        {cv.skills.map((group) => (
          <div key={group.name} className="space-y-3 border-t border-line pt-4">
            <dt className="font-mono text-xs text-accent">{group.name}</dt>
            <dd>
              <ul className="space-y-1.5 text-sm">
                {group.skills.map((skill) => (
                  <li key={skill}>{skill}</li>
                ))}
              </ul>
            </dd>
          </div>
        ))}
      </dl>
    </Chapter>
  )
}
