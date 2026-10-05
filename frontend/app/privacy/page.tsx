import type { Metadata } from 'next'
import { Section } from '@/components/CvBlocks'
import { SiteFooter } from '@/components/SiteFooter'
import { SiteNav } from '@/components/SiteNav'
import { cv } from '@/lib/cv'

export const metadata: Metadata = {
  title: 'Privacy',
  description: `What ${cv.name}'s site stores about you, why, and for how long.`,
}

const linkClass = 'text-accent underline underline-offset-4'

export default function PrivacyPage() {
  const email = cv.links.find((link) => link.name === 'Email')
  const contact = email ? (
    <a href={email.href} className={linkClass}>
      {email.label}
    </a>
  ) : (
    'the email on the CV'
  )

  return (
    <>
      <SiteNav initials={cv.initials} photo={cv.photo} />
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-12 px-6 pt-12 pb-24 sm:px-10">
        <header className="space-y-3">
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">Privacy notice</h1>
          <p className="font-mono text-xs text-muted">Last updated: 5 October 2026</p>
        </header>

        <Section title="who">
          <p className="leading-relaxed">
            This site is run by {cv.name}. Contact: {contact}.
          </p>
        </Section>

        <Section title="if you create an account">
          <ul className="list-disc space-y-1.5 pl-5 leading-relaxed marker:text-line">
            <li>your email address</li>
            <li>your password, stored only as a bcrypt hash, never in plain text</li>
            <li>the company and role you give, if any (both are optional)</li>
            <li>the date you signed up</li>
            <li>the time of your last visit, updated when you sign in or your session refreshes</li>
            <li>
              a record of each sign-in session: a one-way hash of the session token, with when it
              was created, used, expires and was revoked. These keep you signed in and let a stolen
              session be shut down, and they are deleted with your account.
            </li>
          </ul>
          <p className="leading-relaxed">
            Robert&apos;s admin page shows your email, company, role, sign-up date and last visit.
            It never shows your password hash or session records.
          </p>
        </Section>

        <Section title="why">
          <p className="leading-relaxed">
            So Robert knows who viewed his CV. Company and role are optional.
          </p>
        </Section>

        <Section title="cv match analyses">
          <p className="leading-relaxed">
            When you run a match, the job posting, any CV file you upload and the report are held
            temporarily and expire automatically within about an hour.
          </p>
        </Section>

        <Section title="visit statistics">
          <p className="leading-relaxed">
            Visits are counted with Umami, which uses no cookies and does not store your IP address.
            The tracking script is served from this site; the statistics are sent to Umami Cloud,
            which processes them on Robert&apos;s behalf.
          </p>
        </Section>

        <Section title="retention">
          <p className="leading-relaxed">
            Accounts with no activity for 12 months are deleted automatically.
          </p>
        </Section>

        <Section title="your rights">
          <p className="leading-relaxed">
            Email {contact} to see or delete your data. Deletion requests are handled within 30
            days.
          </p>
        </Section>
      </main>
      <SiteFooter />
    </>
  )
}
