import Link from 'next/link'
import { Chapter } from '@/components/CvBlocks'
import { cv } from '@/lib/cv'

export function Skills() {
  return (
    <Chapter
      id="skills"
      index="03"
      title="Skills"
      intro="What the work above is built on. The full inventory, including Java and Spring Boot, is in the CV."
    >
      <dl className="grid gap-x-10 gap-y-8 md:grid-cols-3">
        {cv.featuredSkills.map((group) => (
          <div key={group.name} className="space-y-3 border-t border-line-strong pt-4">
            <dt className="font-semibold">{group.name}</dt>
            <dd>
              <ul className="space-y-1.5 text-muted">
                {group.skills.map((skill) => (
                  <li key={skill}>{skill}</li>
                ))}
              </ul>
            </dd>
          </div>
        ))}
      </dl>
      <Link
        href="/cv"
        className="inline-block rounded-sm py-1 text-sm font-medium text-accent underline underline-offset-4 hover:decoration-2"
      >
        Full skills inventory in the CV →
      </Link>
    </Chapter>
  )
}
