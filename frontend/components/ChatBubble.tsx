'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { Composer } from '@/components/Composer'
import { Transcript } from '@/components/Transcript'
import { showsChatBubble } from '@/lib/bubble'
import { useConversation } from '@/lib/useConversation'

const PANEL_ID = 'chat-bubble-panel'

function SignInPrompt() {
  return (
    <div className="flex flex-col gap-4 p-5">
      <p className="text-sm leading-relaxed">
        Ask anything about my experience, projects, or skills — answered only from my CV, with the
        source extracts attached.
      </p>
      <p className="text-sm text-muted">Sign in to start a conversation.</p>
      <div className="flex items-center gap-4 font-mono text-sm">
        <Link href="/login" className="border border-fg px-3 py-2">
          sign in
        </Link>
        <Link href="/register" className="text-muted underline underline-offset-4">
          create an account
        </Link>
      </div>
    </div>
  )
}

function LiveChat() {
  const { turns, pending, ask } = useConversation()
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [turns.length, pending])

  return (
    <>
      <div className="flex-1 overflow-y-auto p-4">
        <Transcript turns={turns} pending={pending} />
        <div ref={endRef} />
      </div>
      <div className="px-4 pb-3">
        <Composer onAsk={ask} pending={pending} />
      </div>
    </>
  )
}

export function ChatBubble() {
  const pathname = usePathname()
  const { status } = useAuth()
  const [open, setOpen] = useState(false)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)

  function close() {
    returnFocus.current = true
    setOpen(false)
  }

  // Focus after the re-render: on phones the toggle is display:none while the panel is open,
  // and focus() on a hidden element silently does nothing.
  useEffect(() => {
    if (open || !returnFocus.current) return
    returnFocus.current = false
    toggleRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (!open) return
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [open])

  if (!showsChatBubble(pathname)) return null

  return (
    <div className="print:hidden">
      {open ? (
        <section
          id={PANEL_ID}
          role="dialog"
          aria-label="Chat about Robert's CV"
          className={`fixed inset-x-0 bottom-0 z-40 flex flex-col rounded-t-lg border border-line bg-bg shadow-2xl sm:inset-x-auto sm:right-5 sm:bottom-24 sm:w-[380px] sm:rounded-lg ${status === 'authenticated' ? 'h-[85dvh] sm:h-[520px]' : ''}`}
        >
          <header className="flex items-baseline justify-between border-b border-line px-4 py-3">
            <span className="font-mono text-sm">ask my cv</span>
            <span className="flex items-baseline gap-4 font-mono text-xs text-muted">
              {status === 'authenticated' ? (
                <Link href="/chat" className="underline underline-offset-4 hover:text-fg">
                  full screen
                </Link>
              ) : null}
              <button
                type="button"
                onClick={close}
                aria-label="Close chat"
                className="hover:text-fg"
              >
                close
              </button>
            </span>
          </header>
          {status === 'authenticated' ? (
            <LiveChat />
          ) : status === 'anonymous' ? (
            <SignInPrompt />
          ) : (
            <p className="p-5 font-mono text-sm text-muted">checking session…</p>
          )}
        </section>
      ) : null}

      <button
        ref={toggleRef}
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls={PANEL_ID}
        aria-label={open ? 'Close chat' : 'Chat about my CV'}
        className={`fixed right-5 bottom-5 z-50 flex size-14 items-center justify-center rounded-full bg-fg text-bg shadow-lg transition-transform hover:scale-105 ${open ? 'max-sm:hidden' : ''}`}
      >
        {open ? (
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className="size-6"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        ) : (
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className="size-6"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinejoin="round"
          >
            <path d="M4 5h16v11H9l-5 4V5z" />
          </svg>
        )}
      </button>
    </div>
  )
}
