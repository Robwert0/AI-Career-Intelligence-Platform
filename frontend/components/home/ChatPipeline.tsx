// Mirrors backend/app/routes/chat.py and app/ai/rag.py. If that request path changes, change this.
const STEPS: { title: string; detail: string; parts?: string[] }[] = [
  { title: 'Sign-in and rate limits', detail: 'Per IP and per user, enforced in Redis.' },
  {
    title: 'Hybrid retrieval',
    detail: 'Both rankings fused with Reciprocal Rank Fusion.',
    parts: ['pgvector similarity', 'Postgres full-text'],
  },
  { title: 'Relevance gate', detail: 'Off-topic questions are refused before the model runs.' },
  {
    title: 'Local LLM',
    detail: 'System prompt, question and CV extracts in separate, escaped channels.',
  },
  { title: 'Output check', detail: 'An answer that leaks the prompt is replaced by a refusal.' },
  { title: 'Answer with sources', detail: 'The CV passages it drew on are returned with it.' },
]

export function ChatPipeline() {
  return (
    <figure className="rounded-lg border border-line bg-bg p-5 sm:p-6">
      <figcaption className="font-mono text-xs text-subtle">
        How the site answers a chat question
      </figcaption>
      <ol className="mt-5 grid gap-4 sm:grid-cols-2 sm:gap-x-6 sm:gap-y-5 lg:grid-cols-3">
        {STEPS.map((step, index) => (
          <li key={step.title} className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3">
            {index < STEPS.length - 1 ? (
              <span
                aria-hidden="true"
                className="absolute top-7 bottom-[-1rem] left-[0.8125rem] w-px bg-line-strong sm:hidden"
              />
            ) : null}
            <span
              aria-hidden="true"
              className="relative flex size-7 items-center justify-center rounded-full border border-accent/60 bg-bg font-mono text-xs text-accent"
            >
              {index + 1}
            </span>
            <div className="space-y-1.5 pt-0.5">
              <p className="text-sm font-medium">{step.title}</p>
              {step.parts ? (
                <ul className="flex flex-wrap gap-1.5">
                  {step.parts.map((part) => (
                    <li
                      key={part}
                      className="rounded-sm border border-line-strong px-2 py-0.5 font-mono text-xs text-muted"
                    >
                      {part}
                    </li>
                  ))}
                </ul>
              ) : null}
              <p className="text-sm leading-relaxed text-muted">{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </figure>
  )
}
