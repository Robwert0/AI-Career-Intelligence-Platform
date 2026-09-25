import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { Highlights, Section, Tags } from '@/components/CvBlocks'
import { getProject, projects } from '@/lib/projects'

export const dynamicParams = false

export function generateStaticParams() {
  return projects.map((project) => ({ slug: project.slug }))
}

export async function generateMetadata({
  params,
}: PageProps<'/projects/[slug]'>): Promise<Metadata> {
  const project = getProject((await params).slug)
  if (!project) return {}
  return { title: `${project.name} — Robert Mirea`, description: project.tagline }
}

export default async function ProjectPage({ params }: PageProps<'/projects/[slug]'>) {
  const project = getProject((await params).slug)
  if (!project) notFound()

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 space-y-12 px-4 pt-16 pb-32">
      <Link
        href="/#projects"
        className="inline-block font-mono text-xs text-accent underline underline-offset-4"
      >
        ← back to projects
      </Link>

      <header className="space-y-3">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{project.name}</h1>
        <p className="text-lg text-muted">{project.tagline}</p>
        <p className="font-mono text-xs text-muted">
          {project.context} · {project.period}
        </p>
      </header>

      <Section title="what it does">
        <p className="max-w-prose leading-relaxed">{project.purpose}</p>
      </Section>

      <Section title="about">
        <p className="max-w-prose leading-relaxed">{project.description}</p>
      </Section>

      <Section title="highlights">
        <Highlights items={project.highlights} />
      </Section>

      <Section title="skills used">
        <Tags items={project.stack} />
      </Section>

      <Section title="source">
        {project.repos.length > 0 ? (
          <ul className="space-y-1 font-mono text-xs">
            {project.repos.map((repo) => (
              <li key={repo}>
                <a
                  href={repo}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent underline underline-offset-4"
                >
                  {repo.replace('https://', '')} ↗
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Private repository.</p>
        )}
      </Section>
    </main>
  )
}
