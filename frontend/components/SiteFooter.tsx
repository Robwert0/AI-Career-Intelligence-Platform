import { cv } from '@/lib/cv'
import { getProject } from '@/lib/projects'

export function SiteFooter() {
  const source = getProject('ai-career-intelligence-platform')?.repos[0]
  return (
    <footer className="mx-auto flex w-full max-w-5xl flex-wrap justify-between gap-4 border-t border-line px-4 py-8 font-mono text-xs text-muted sm:px-6 print:hidden">
      <p>
        © {new Date().getFullYear()} {cv.name}
      </p>
      <p>
        Built with Next.js and FastAPI
        {source ? (
          <>
            {' · '}
            <a
              href={source}
              target="_blank"
              rel="noopener noreferrer"
              className="underline decoration-line-strong underline-offset-4 hover:text-fg"
            >
              source ↗
            </a>
          </>
        ) : null}
      </p>
    </footer>
  )
}
