import Image from 'next/image'
import Link from 'next/link'
import { LinkIcon } from '@/components/LinkIcon'
import { AskCv } from '@/components/home/AskCv'
import { cv } from '@/lib/cv'

const buttonBase =
  'inline-flex items-center justify-center rounded-md px-5 py-3 text-sm font-medium transition-colors'

// The skills and education chapters repeat the rest, so phones get only these two.
const PHONE_FACTS = new Set(['role', 'location'])

export function Hero() {
  return (
    <section
      aria-labelledby="hero-title"
      className="grid gap-8 pt-8 sm:pt-16 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-center lg:gap-x-16 lg:gap-y-10 lg:pt-20"
    >
      <div className="enter space-y-6 sm:space-y-7">
        <div className="space-y-4">
          <p className="font-mono text-xs tracking-wide text-accent">{cv.title}</p>
          <h1
            id="hero-title"
            className="text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl"
          >
            {cv.name}
          </h1>
          <p className="max-w-2xl text-2xl leading-snug font-medium tracking-tight text-balance sm:text-3xl">
            {cv.headline}
          </p>
        </div>
        <p className="max-w-2xl text-lg leading-relaxed text-muted">{cv.intro}</p>

        <div className="flex flex-wrap gap-3">
          <Link href="/#work" className={`${buttonBase} bg-accent text-on-accent hover:opacity-90`}>
            Explore my work
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

        <ul className="flex flex-wrap gap-x-2 gap-y-1" aria-label="Contact and profiles">
          {cv.links.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                {...(link.href.startsWith('https:')
                  ? { target: '_blank', rel: 'noopener noreferrer' }
                  : {})}
                className="-mx-1 inline-flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted transition-colors hover:bg-surface hover:text-fg"
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
        className="enter flex items-center gap-4 [animation-delay:120ms] max-lg:order-first lg:block lg:rounded-lg lg:border lg:border-line lg:bg-surface lg:p-6"
      >
        {cv.photo ? (
          <Image
            src={cv.photo.src}
            alt={cv.photo.alt}
            width={240}
            height={240}
            loading="eager"
            className="size-16 shrink-0 rounded-full border border-line object-cover lg:mb-6 lg:size-30"
          />
        ) : null}
        <dl className="space-y-0.5 lg:space-y-4">
          {cv.glance.map((fact) => (
            <div
              key={fact.label}
              className={`lg:space-y-1 ${PHONE_FACTS.has(fact.label) ? '' : 'hidden lg:block'}`}
            >
              <dt className="font-mono text-xs tracking-wider text-subtle uppercase max-lg:sr-only">
                {fact.label}
              </dt>
              <dd
                className={`text-sm leading-relaxed ${fact.label === 'role' ? 'font-medium' : 'max-lg:text-muted'}`}
              >
                {fact.value}
              </dd>
            </div>
          ))}
        </dl>
      </aside>

      <div className="enter [animation-delay:200ms] lg:col-span-2">
        <AskCv />
      </div>
    </section>
  )
}
