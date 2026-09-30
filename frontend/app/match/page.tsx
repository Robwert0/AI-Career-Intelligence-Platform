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
      <SiteNav initials={cv.initials} photo={cv.photo} />
      <main className="mx-auto w-full max-w-[72rem] flex-1 px-4 pt-8 pb-24 sm:px-10 sm:pt-12">
        <MatchGate />
      </main>
    </>
  )
}
