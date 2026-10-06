'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { Composer } from '@/components/Composer'
import { Transcript } from '@/components/Transcript'
import { showsChatBubble } from '@/lib/bubble'
import { CHAT_ENTRY_SELECTOR, OPEN_CHAT_EVENT } from '@/lib/chatLauncher'
import { useConversation } from '@/lib/useConversation'

const PANEL_ID = 'chat-bubble-panel'

function canFocus(element: HTMLElement | null | undefined): element is HTMLElement {
  return (
    element != null &&
    element !== document.body &&
    element.isConnected &&
    element.checkVisibility?.() !== false
  )
}

function SignInPrompt() {
  return (
    <div className="flex flex-col gap-4 p-5">
      <p className="text-sm leading-relaxed">
        Ask anything about my experience, projects, or skills — answered only from my CV, with the
        source extracts attached.
      </p>
      <p className="text-sm text-muted">
        The chat requires an account: sign in, or create one, to start a conversation.
      </p>
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
        <Transcript turns={turns} pending={pending} onAsk={ask} />
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
  const { status, accountId } = useAuth()
  const [open, setOpen] = useState(false)
  const [entryInView, setEntryInView] = useState(false)
  const toggleRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const returnFocus = useRef(false)

  function show(trigger: HTMLElement | null) {
    opener.current =
      trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null)
    // Already open: setOpen(true) changes nothing, so the focus effect wouldn't run again.
    panelRef.current?.focus()
    setOpen(true)
  }

  function close() {
    returnFocus.current = true
    setOpen(false)
  }

  useEffect(() => {
    const visible = new Set<Element>()
    const observer = new IntersectionObserver((changes) => {
      for (const change of changes) {
        if (change.isIntersecting) visible.add(change.target)
        else visible.delete(change.target)
      }
      setEntryInView(visible.size > 0)
    })
    document.querySelectorAll(CHAT_ENTRY_SELECTOR).forEach((entry) => observer.observe(entry))
    return () => {
      observer.disconnect()
      setEntryInView(false)
    }
  }, [pathname])

  useEffect(() => {
    if (!showsChatBubble(pathname)) return
    function onOpen(event: Event) {
      show(
        event instanceof CustomEvent && event.detail instanceof HTMLElement ? event.detail : null,
      )
    }
    window.addEventListener(OPEN_CHAT_EVENT, onOpen)
    return () => window.removeEventListener(OPEN_CHAT_EVENT, onOpen)
  }, [pathname])

  // Focus after the re-render: on phones the toggle is display:none while the panel is open,
  // and focus() on a hidden element silently does nothing.
  useEffect(() => {
    if (open) {
      panelRef.current?.focus()
      return
    }
    if (!returnFocus.current) return
    returnFocus.current = false
    // The opener can be gone or hidden by now: the launcher steps aside for an inline entry.
    const entry = document.querySelector<HTMLElement>(`${CHAT_ENTRY_SELECTOR} button`)
    const target = [opener.current, entry, toggleRef.current].find(canFocus)
    target?.focus()
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
          ref={panelRef}
          id={PANEL_ID}
          tabIndex={-1}
          role="dialog"
          aria-label="Chat about Robert's CV"
          className={`fixed inset-x-0 bottom-0 z-40 flex flex-col rounded-t-lg border border-line bg-bg shadow-2xl sm:inset-x-auto sm:right-5 sm:bottom-24 sm:w-[380px] sm:rounded-lg focus:outline-none ${status === 'authenticated' ? 'h-[85dvh] sm:h-[520px]' : ''}`}
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
            // Keyed by account so a sign-out or account switch never carries context over.
            <LiveChat key={accountId ?? 'unknown'} />
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
        onClick={(event) => (open ? close() : show(event.currentTarget))}
        aria-expanded={open}
        aria-controls={PANEL_ID}
        aria-label={open ? 'Close chat' : undefined}
        className={`fixed right-4 bottom-4 z-50 flex items-center justify-center gap-2 rounded-full bg-fg text-bg shadow-lg transition-transform hover:scale-105 motion-reduce:transition-none motion-reduce:hover:scale-100 sm:right-5 sm:bottom-5 ${open ? 'size-14 max-sm:hidden' : `size-12 sm:h-12 sm:w-auto sm:px-5 ${entryInView ? 'hidden' : ''}`}`}
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
        {open ? null : (
          <span className="text-sm font-medium max-sm:sr-only">Ask about my experience</span>
        )}
      </button>
      {/* Lets the page scroll its last lines and controls clear of the floating launcher. */}
      <div aria-hidden="true" className="h-20" />
    </div>
  )
}
