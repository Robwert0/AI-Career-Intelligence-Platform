import Image from 'next/image'
import Link from 'next/link'
import { LinkIcon } from '@/components/LinkIcon'
import { cv } from '@/lib/cv'

const buttonBase =
  'inline-flex items-center justify-center rounded-md px-4 py-2.5 text-sm font-medium transition-colors'

export function Hero() {
  return (
    <section
      aria-labelledby="hero-title"
      className="grid gap-10 pt-14 sm:pt-20 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-center lg:gap-16"
    >
      <div className="enter space-y-7">
        <div className="space-y-4">
          <p className="font-mono text-xs tracking-wide text-accent">{cv.title}</p>
          <h1 id="hero-title" className="text-4xl font-medium tracking-tight sm:text-5xl">
            {cv.name}
          </h1>
          <p className="max-w-2xl text-xl leading-snug text-fg sm:text-2xl">{cv.headline}</p>
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

        <ul className="flex flex-wrap gap-x-2 gap-y-2" aria-label="Contact and profiles">
          {cv.links.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                {...(link.href.startsWith('https:')
                  ? { target: '_blank', rel: 'noopener noreferrer' }
                  : {})}
                className="-mx-1 inline-flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted transition-colors hover:bg-surface hover:text-fg"
              >
                <LinkIcon name={link.name} />
                {link.name}
              </a>
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
            className="mb-6 size-20 rounded-full border border-line object-cover"
          />
        ) : null}
        <dl className="space-y-4">
          {cv.glance.map((fact) => (
            <div key={fact.label} className="space-y-1">
              <dt className="font-mono text-[11px] tracking-wider text-subtle uppercase">
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
