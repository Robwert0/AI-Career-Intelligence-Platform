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

        <Section title="for every visitor">
          <ul className="list-disc space-y-1.5 pl-5 leading-relaxed marker:text-line">
            <li>
              Rate limiting: your IP address is held briefly in Redis to protect the site from
              abuse, and expires automatically within about an hour. If you are signed in, your
              account id is used the same way.
            </li>
            <li>
              Server logs: the server&apos;s request logs record your IP address and the page or API
              path requested. For chat they also record your pseudonymous account id, the AI model
              used, usage figures (token counts and response time) and technical details: whether
              your message matched known prompt-injection phrasing (and which patterns), whether the
              answer was refused or incomplete (with the search relevance score or the check that
              failed), and, for a blocked answer, a short fingerprint and its length, never its
              text. They are kept for security and troubleshooting and deleted after 30 days.
            </li>
          </ul>
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
            A sign-in cookie (httpOnly, so page scripts cannot read it) holds your session token so
            you stay signed in. It is needed for sign-in, is not used for tracking, lasts up to 7
            days from your last sign-in or session refresh, and is cleared when you sign out.
          </p>
          <p className="leading-relaxed">
            Robert&apos;s admin page shows your email, company, role, sign-up date and last visit.
            It never shows your password hash or session records.
          </p>
        </Section>

        <Section title="why, and on what basis">
          <p className="leading-relaxed">
            Account data and server logs are processed on the basis of legitimate interest: running
            and securing the site, and letting Robert know who viewed his CV. The company and role
            are optional; you give them with your consent and can have them removed on request.
          </p>
        </Section>

        <Section title="cv match analyses">
          <p className="leading-relaxed">
            When you run a match, the job posting, any CV file you upload and the report are held
            temporarily and expire automatically within about an hour.
          </p>
          <p className="leading-relaxed">
            So a reload does not lose a running analysis or its report, this browser tab keeps two
            identifiers in its session storage: the analysis id and your account id. No CV, job text
            or report is stored in the browser. Session storage is cleared when you close the tab or
            sign out, or when another account signs in. Keeping the identifiers does not make the
            analysis last longer: the report is still deleted on the server when it expires.
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
            days. You can also complain to the data protection authority in your country.
          </p>
        </Section>
      </main>
      <SiteFooter />
    </>
  )
}
