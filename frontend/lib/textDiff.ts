export type DiffSegment = { text: string; changed: boolean }
export type WordDiff = { original: DiffSegment[]; suggested: DiffSegment[] }

// Longest-common-subsequence over whitespace-separated words, so a rewrite shows which words it
// removed and which it added. Whitespace stays attached to the word before it, and each side keeps
// its own spelling.
export function wordDiff(before: string, after: string): WordDiff {
  const a = tokens(before)
  const b = tokens(after)
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => Array(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = same(a[i], b[j]) ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const original: DiffSegment[] = []
  const suggested: DiffSegment[] = []
  let i = 0
  let j = 0
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && same(a[i], b[j])) {
      push(original, a[i++], false)
      push(suggested, b[j++], false)
    } else if (j < b.length && (i === a.length || lcs[i][j + 1] >= lcs[i + 1][j])) {
      push(suggested, b[j++], true)
    } else {
      push(original, a[i++], true)
    }
  }
  return { original, suggested }
}

// Case-insensitive, so moving a word to the start of the sentence isn't reported as a rewrite.
function same(left: string, right: string): boolean {
  return left.trim().toLowerCase() === right.trim().toLowerCase()
}

function tokens(text: string): string[] {
  return text.match(/\S+\s*/g) ?? []
}

function push(segments: DiffSegment[], text: string, changed: boolean) {
  const last = segments.at(-1)
  if (last && last.changed === changed) last.text += text
  else segments.push({ text, changed })
}
