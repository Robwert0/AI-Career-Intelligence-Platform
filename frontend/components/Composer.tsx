'use client'

import { useState } from 'react'

const MAX_MESSAGE = 2000

export function Composer({
  onAsk,
  pending,
}: {
  onAsk: (message: string) => void
  pending: boolean
}) {
  const [message, setMessage] = useState('')
  const trimmed = message.trim()
  const tooLong = message.length > MAX_MESSAGE
  const canSend = trimmed.length > 0 && !tooLong && !pending

  function submit() {
    if (!canSend) return
    onAsk(trimmed)
    setMessage('')
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
      className="border-t border-line pt-3"
    >
      <label className="sr-only" htmlFor="question">
        Ask about the CV
      </label>
      <textarea
        id="question"
        rows={2}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault()
            submit()
          }
        }}
        placeholder="ask about the CV…"
        className="w-full resize-none bg-transparent font-mono text-sm outline-none placeholder:text-muted"
      />
      <div className="flex items-baseline justify-between font-mono text-xs">
        <span className="text-muted">enter to send · shift+enter for a new line</span>
        <span className={tooLong ? 'text-danger' : 'text-muted'}>
          {message.length}/{MAX_MESSAGE}
        </span>
      </div>
    </form>
  )
}
