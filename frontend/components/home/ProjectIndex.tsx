import Link from 'next/link'
import { Chapter } from '@/components/CvBlocks'
import { cv } from '@/lib/cv'
import type { ProjectCategory } from '@/lib/projects'

const CATEGORY_LABEL: Record<ProjectCategory, string> = {
  flagship: 'this site',
  featured: 'featured',
  internship: 'internship',
  learning: 'learning',
}

export function ProjectIndex() {
  return (
    <Chapter
      id="projects"
      index="04"
      title="All projects"
      intro="Everything on my GitHub, from production-minded builds to the exercises I learned on. Each has its own page."
    >
      <ul className="divide-y divide-line border-y border-line">
        {cv.projects.map((project) => (
          <li key={project.slug}>
            <Link
              href={`/projects/${project.slug}`}
              className="group grid gap-1 py-4 transition-colors sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_6rem_1rem] sm:items-baseline sm:gap-6"
            >
              <span className="font-medium transition-colors group-hover:text-accent">
                {project.name}
              </span>
              <span className="text-sm text-muted">{project.tagline}</span>
              <span className="font-mono text-[11px] text-muted sm:text-right">
                {CATEGORY_LABEL[project.category]}
              </span>
              <span
                aria-hidden="true"
                className="hidden text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-accent sm:block"
              >
                →
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </Chapter>
  )
}
