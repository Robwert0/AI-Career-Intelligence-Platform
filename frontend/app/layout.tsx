import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import Script from 'next/script'
import { AuthProvider } from '@/components/AuthProvider'
import { ChatBubble } from '@/components/ChatBubble'
import { themeInitScript } from '@/lib/theme'
import './globals.css'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

const umamiWebsiteId = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID
const umamiDomains = process.env.NEXT_PUBLIC_UMAMI_DOMAINS
// The vendored tracker's built-in default; pinned so it matches the CSP connect-src exactly.
const UMAMI_HOST_URL = 'https://gateway.umami.is'

export const metadata: Metadata = {
  title: 'Robert Mirea — Backend & AI Engineer',
  description:
    'Backend and AI engineer: Python/FastAPI microservices, LLM reliability, RAG systems. Ask my CV anything.',
}

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="flex min-h-full flex-col">
        <AuthProvider>
          {children}
          <ChatBubble />
        </AuthProvider>
        {umamiWebsiteId ? (
          <Script
            src="/umami.js"
            data-website-id={umamiWebsiteId}
            data-domains={umamiDomains}
            data-host-url={UMAMI_HOST_URL}
            strategy="afterInteractive"
          />
        ) : null}
      </body>
    </html>
  )
}
