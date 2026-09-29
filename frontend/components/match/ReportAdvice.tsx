import type { MatchReport, Recommendation } from '@/lib/match'
import { citation, evidenceById, requirementTextById } from '@/lib/matchReport'
import { SECTION_TITLE } from './styles'

export function Improvements({ report }: { report: MatchReport }) {
  const { immediate, longer_term: longerTerm } = report.recommendations
  if (immediate.length === 0 && longerTerm.length === 0) return null
  const names = requirementTextById(report)
  return (
    <section aria-labelledby="improve-title" className="space-y-6">
      <h2 id="improve-title" className={SECTION_TITLE}>
        Where to improve
      </h2>
      <div className="grid gap-8 md:grid-cols-2">
        <RecommendationGroup title="For this application" items={immediate} names={names} />
        <RecommendationGroup title="Longer-term development" items={longerTerm} names={names} />
      </div>
    </section>
  )
}

function RecommendationGroup({
  title,
  items,
  names,
}: {
  title: string
  items: Recommendation[]
  names: Map<string, string>
}) {
  return (
    <div className="space-y-3">
      <h3 className="font-medium">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted">Nothing to add here.</p>
      ) : (
        <ul className="space-y-4">
          {items.map((item, index) => {
            const requirement = names.get(item.requirement_id)
            return (
              <li
                key={`${item.requirement_id}-${index}`}
                className="space-y-1 border-l-2 border-line pl-4"
              >
                <p className="font-medium">{item.title}</p>
                <p className="text-sm leading-relaxed text-muted">{item.detail}</p>
                {requirement ? (
                  <p className="font-mono text-xs text-subtle">For: {requirement}</p>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

export function SuggestedWording({ report }: { report: MatchReport }) {
  if (report.rewrites.length === 0) return null
  const sources = evidenceById(report)
  return (
    <section aria-labelledby="wording-title" className="space-y-6">
      <h2 id="wording-title" className={SECTION_TITLE}>
        Suggested CV wording
      </h2>
      <p className="text-sm text-muted">
        Each rewrite uses facts already in your evidence. Where a stronger line needs a fact we
        don&apos;t have, we ask for it instead of inventing it.
      </p>
      <ul className="space-y-6">
        {report.rewrites.map((rewrite, index) => {
          const source = sources.get(rewrite.evidence_id)
          return (
            <li
              key={`${rewrite.evidence_id}-${index}`}
              className="space-y-3 rounded-lg border border-line p-4"
            >
              <p className="font-mono text-xs text-accent">
                {source ? citation(source).label : 'CV'}
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <p className="font-mono text-xs text-muted">Before</p>
                  <p className="text-sm leading-relaxed">{rewrite.before}</p>
                </div>
                <div className="space-y-1">
                  <p className="font-mono text-xs text-muted">After</p>
                  <p className="text-sm leading-relaxed">{rewrite.after}</p>
                </div>
              </div>
              {rewrite.questions.length > 0 ? (
                <div className="space-y-1">
                  <p className="font-mono text-xs text-muted">To make it stronger, answer:</p>
                  <ul className="list-disc space-y-1 pl-5 text-sm">
                    {rewrite.questions.map((question) => (
                      <li key={question}>{question}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
