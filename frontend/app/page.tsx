import { SiteFooter } from '@/components/SiteFooter'
import { SiteNav } from '@/components/SiteNav'
import { Contact, Education } from '@/components/home/Closing'
import { Experience } from '@/components/home/Experience'
import { Hero } from '@/components/home/Hero'
import { SelectedWork } from '@/components/home/SelectedWork'
import { Skills } from '@/components/home/Skills'
import { cv } from '@/lib/cv'
import { CONTAINER } from '@/lib/layout'

export default function Home() {
  return (
    <>
      <SiteNav initials={cv.initials} photo={cv.photo} />
      <main className={`${CONTAINER} flex-1 space-y-20 pb-20 sm:space-y-28 sm:pb-24`}>
        <Hero />
        <SelectedWork />
        <Experience />
        <Skills />
        <Education />
        <Contact />
      </main>
      <SiteFooter />
    </>
  )
}
