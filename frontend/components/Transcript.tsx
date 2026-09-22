import { SourcesPanel } from '@/components/SourcesPanel'
import type { Turn } from '@/lib/turns'

function TurnBody({ turn }: { turn: Turn }) {
  switch (turn.kind) {
    case 'question':
      return (
        <p className="font-mono text-sm">
          <span className="text-accent">&gt; </span>
          {turn.text}
        </p>
      )
    case 'answer':
      return (
        <div>
          <p className="max-w-prose leading-relaxed">{turn.text}</p>
          <SourcesPanel sources={turn.sources} />
        </div>
      )
    case 'refusal':
      return <p className="max-w-prose text-muted italic">{turn.text}</p>
    case 'error':
      return <p className="font-mono text-sm text-danger">{turn.text}</p>
  }
}

export function Transcript({ turns, pending }: { turns: Turn[]; pending: boolean }) {
  if (turns.length === 0 && !pending) {
    return (
      <p className="font-mono text-sm text-muted">
        Ask something the CV can answer — experience, skills, education.
      </p>
    )
  }

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
