import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { AuthProvider } from '@/components/AuthProvider'
import { ChatBubble } from '@/components/ChatBubble'
import './globals.css'

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
})

export const metadata: Metadata = {
  title: 'Robert Mirea — Software Engineer',
  description:
    'Backend software engineer: Python microservices, event-driven systems, PostgreSQL/pgvector. Ask my CV anything.',
}

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <AuthProvider>
          {children}
          <ChatBubble />
        </AuthProvider>
      </body>
    </html>
  )
}
