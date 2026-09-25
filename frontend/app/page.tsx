import { SiteFooter } from '@/components/SiteFooter'
import { SiteNav } from '@/components/SiteNav'
import { Contact, Education } from '@/components/home/Closing'
import { Experience } from '@/components/home/Experience'
import { Hero } from '@/components/home/Hero'
import { ProjectIndex } from '@/components/home/ProjectIndex'
import { SelectedWork } from '@/components/home/SelectedWork'
import { Skills } from '@/components/home/Skills'
import { cv } from '@/lib/cv'

export default function Home() {
  return (
    <>
      <SiteNav initials={cv.initials} />
      <main className="mx-auto w-full max-w-5xl flex-1 space-y-28 px-4 pb-28 sm:px-6">
        <Hero />
        <SelectedWork />
        <Experience />
        <Skills />
        <ProjectIndex />
        <Education />
        <Contact />
      </main>
      <SiteFooter />
    </>
  )
}
