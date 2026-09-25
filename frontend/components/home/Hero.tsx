import Image from 'next/image'
import Link from 'next/link'
import { cv } from '@/lib/cv'

const buttonBase =
  'inline-flex items-center justify-center rounded-md px-4 py-2.5 text-sm font-medium transition-colors'

function External({ href, children }: { href: string; children: React.ReactNode }) {
  const isWeb = href.startsWith('https:')
  return (
    <a
      href={href}
      {...(isWeb ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      className="font-mono text-xs text-muted underline decoration-line-strong underline-offset-4 transition-colors hover:text-fg hover:decoration-accent"
    >
      {children}
    </a>
  )
}

export function Hero() {
  return (
    <section
      aria-labelledby="hero-title"
      className="grid gap-12 pt-12 sm:pt-20 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-end lg:gap-16"
    >
      <div className="enter space-y-8">
        <div className="space-y-4">
          <p className="font-mono text-xs tracking-wide text-accent">{cv.title}</p>
          <h1 id="hero-title" className="text-4xl font-medium tracking-tight sm:text-5xl">
            {cv.name}
          </h1>
          <p className="max-w-2xl text-xl leading-snug text-fg/90 sm:text-2xl">{cv.headline}</p>
        </div>
        <p className="max-w-2xl leading-relaxed text-muted">{cv.intro}</p>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/#experience"
            className={`${buttonBase} bg-accent text-on-accent hover:opacity-90`}
          >
            View experience
          </Link>
          <Link
            href="/cv"
            className={`${buttonBase} border border-line-strong hover:border-accent hover:text-accent`}
          >
            View CV
          </Link>
          {cv.pdf ? (
            <a
              href={cv.pdf.href}
              download
              className={`${buttonBase} border border-line-strong hover:border-accent hover:text-accent`}
            >
              Download CV
            </a>
          ) : null}
        </div>

        <ul className="flex flex-wrap gap-x-6 gap-y-2">
          {cv.links.map((link) => (
            <li key={link.href}>
              <External href={link.href}>{link.label}</External>
            </li>
          ))}
        </ul>
      </div>

      <aside
        aria-label="At a glance"
        className="enter rounded-lg border border-line bg-surface p-6 [animation-delay:120ms]"
      >
        {cv.photo ? (
          <Image
            src={cv.photo.src}
            alt={cv.photo.alt}
            width={160}
            height={160}
            loading="eager"
            className="mb-6 size-20 rounded-md border border-line object-cover"
          />
        ) : null}
        <dl className="space-y-4">
          {cv.glance.map((fact) => (
            <div key={fact.label} className="space-y-1">
              <dt className="font-mono text-[11px] tracking-wider text-muted uppercase">
                {fact.label}
              </dt>
              <dd className="text-sm leading-relaxed">{fact.value}</dd>
            </div>
          ))}
        </dl>
      </aside>
    </section>
  )
}
