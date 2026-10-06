import { SourcesPanel } from '@/components/SourcesPanel'
import { CHAT_STARTERS } from '@/lib/chatStarters'
import type { Turn } from '@/lib/turns'

function TurnBody({ turn }: { turn: Turn }) {
  switch (turn.kind) {
    case 'question':
      return (
        <p className="font-mono text-sm break-words">
          <span className="text-accent">&gt; </span>
          {turn.text}
        </p>
      )
    case 'answer':
      return (
        <div>
          <p className="max-w-prose leading-relaxed break-words">{turn.text}</p>
          <SourcesPanel sources={turn.sources} />
        </div>
      )
    case 'refusal':
      return <p className="max-w-prose break-words text-muted italic">{turn.text}</p>
    case 'error':
      return <p className="font-mono text-sm break-words text-danger">{turn.text}</p>
  }
}

function Starters({ onAsk }: { onAsk: (question: string) => void }) {
  return (
    <div className="space-y-3">
      <p className="font-mono text-sm text-muted">
        Ask something the CV can answer — experience, skills, education. Follow-up questions work
        too.
      </p>
      <ul aria-label="Suggested questions" className="flex flex-col items-start gap-2">
        {CHAT_STARTERS.map((question) => (
          <li key={question}>
            <button
              type="button"
              onClick={() => onAsk(question)}
              className="rounded-md border border-line px-3 py-1.5 text-left text-sm transition-colors hover:border-accent hover:text-accent"
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function Transcript({
  turns,
  pending,
  onAsk,
}: {
  turns: Turn[]
  pending: boolean
  onAsk: (question: string) => void
}) {
  if (turns.length === 0 && !pending) return <Starters onAsk={onAsk} />

  return (
    <div aria-live="polite" aria-label="Conversation" className="flex flex-col gap-6">
      {turns.map((turn) => (
        <TurnBody key={turn.id} turn={turn} />
      ))}
      {pending ? (
        <p className="font-mono text-sm text-muted">
          <span className="animate-pulse">{'█'}</span> thinking…
        </p>
      ) : null}
    </div>
  )
}
