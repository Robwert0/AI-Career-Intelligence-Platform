import type { Metadata } from 'next'
import { SampleReport } from '@/components/match/SampleReport'
import { SiteNav } from '@/components/SiteNav'
import { cv } from '@/lib/cv'

export const metadata: Metadata = {
  title: 'Sample match report — Job Match Analyzer',
  description:
    'A full Job Match Analyzer report for a fictional candidate and job: cited evidence, gaps, next steps and suggested CV wording.',
}

export default function SampleMatchPage() {
  return (
    <>
      <SiteNav initials={cv.initials} photo={cv.photo} />
      <main className="mx-auto w-full max-w-[72rem] flex-1 px-4 pt-8 pb-24 sm:px-10 sm:pt-12">
        <SampleReport />
      </main>
    </>
  )
}
