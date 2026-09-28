import type { Metadata } from 'next'
import { MatchGate } from '@/components/match/MatchGate'
import { SiteNav } from '@/components/SiteNav'
import { cv } from '@/lib/cv'

export const metadata: Metadata = {
  title: 'Job Match Analyzer — Robert Mirea',
  description:
    'Compare your CV and public GitHub work with a job posting: an explainable alignment estimate with cited evidence and concrete improvements.',
}

export default function MatchPage() {
  return (
    <>
      <SiteNav initials={cv.initials} />
      <main className="mx-auto w-full max-w-4xl flex-1 space-y-10 px-4 pt-10 pb-24 sm:px-10">
        <header className="space-y-4">
          <p className="font-mono text-xs text-accent">tool</p>
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">Job Match Analyzer</h1>
          <p className="max-w-2xl leading-relaxed text-muted">
            Add a job posting, by link or pasted text, and your CV and/or public GitHub profile. You
            get an alignment estimate that shows its working: each requirement, the evidence behind
            it, what to improve, and grounded CV wording.
          </p>
        </header>
        <MatchGate />
      </main>
    </>
  )
}
