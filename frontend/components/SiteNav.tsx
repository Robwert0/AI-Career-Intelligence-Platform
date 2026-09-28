'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { ThemeToggle } from '@/components/ThemeToggle'
import { CONTAINER } from '@/lib/layout'
import { NAV_LINKS } from '@/lib/nav'

export function SiteNav({ initials }: { initials: string }) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const linkClass =
    'rounded-md px-3 py-2 text-sm text-muted transition-colors hover:bg-surface hover:text-fg'

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg print:hidden">
      <nav
        aria-label="Main"
        className={`${CONTAINER} flex h-16 items-center justify-between gap-4`}
      >
        <Link
          href="/"
          className="flex items-center gap-2.5 font-mono text-sm tracking-tight"
          onClick={() => setOpen(false)}
        >
          <span
            aria-hidden="true"
            className="flex size-8 items-center justify-center rounded-md border border-line-strong text-xs text-accent"
          >
            {initials}
          </span>
          <span className="hidden sm:inline">Robert Mirea</span>
          <span className="sr-only sm:hidden">Robert Mirea, home</span>
        </Link>

        <ul className="hidden items-center gap-1 md:flex">
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <Link href={link.href} className={linkClass}>
                {link.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link
            href="/cv"
            className="rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-on-accent transition-opacity hover:opacity-90"
          >
            View CV
          </Link>
          <button
            type="button"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((value) => !value)}
            className="inline-flex size-9 items-center justify-center rounded-md border border-line text-muted hover:text-fg md:hidden"
          >
            <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="size-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            >
              {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </nav>

      {open ? (
        <ul id="mobile-nav" className="space-y-1 border-t border-line px-6 py-3 sm:px-10 md:hidden">
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className={`block ${linkClass}`}
                onClick={() => setOpen(false)}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </header>
  )
}
