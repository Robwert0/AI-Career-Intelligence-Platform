'use client'

import { useAuth } from '@/components/AuthProvider'
import { openChatBubble } from '@/lib/chatLauncher'

export function AskCv() {
  const { status } = useAuth()
  return (
    <div
      data-chat-entry
      className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:p-5"
    >
      <div className="space-y-1">
        <p className="font-medium">Ask about my experience</p>
        <p className="text-sm leading-relaxed text-muted">
          Answers come only from my CV and show the passages they used.
          {status === 'authenticated' ? null : ' Requires signing in.'}
        </p>
      </div>
      <button
        type="button"
        onClick={openChatBubble}
        aria-haspopup="dialog"
        className="inline-flex shrink-0 items-center justify-center gap-2 rounded-md border border-line-strong px-4 py-2.5 text-sm font-medium transition-colors hover:border-accent hover:text-accent"
      >
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          className="size-4"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinejoin="round"
        >
          <path d="M4 5h16v11H9l-5 4V5z" />
        </svg>
        {status === 'authenticated' ? 'Open the chat' : 'Ask my CV'}
      </button>
    </div>
  )
}
