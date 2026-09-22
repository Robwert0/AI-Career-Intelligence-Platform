import type { Source } from '@/lib/api'

export function SourcesPanel({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null

  return (
    <details className="group mt-3">
      <summary className="cursor-pointer font-mono text-xs text-muted marker:content-['']">
        <span className="text-accent">{'▸'}</span>
        <span className="group-open:hidden"> sources ({sources.length})</span>
        <span className="hidden group-open:inline"> sources</span>
      </summary>
      <ul className="mt-2 divide-y divide-line border border-line">
        {sources.map((source, index) => (
          <li key={`${source.section}-${index}`} className="px-3 py-2">
            <span className="font-mono text-xs text-accent">[{source.section}]</span>
            <p className="mt-1 text-sm text-muted">{source.content}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}
