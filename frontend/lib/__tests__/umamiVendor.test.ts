import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const PUBLIC_DIR = join(__dirname, '..', '..', 'public')

describe('vendored umami tracker', () => {
  it('matches the sha256 recorded in its README, so a hand edit cannot slip through', () => {
    const readme = readFileSync(join(PUBLIC_DIR, 'umami.README.md'), 'utf8')
    const recorded = readme.match(/sha256: `([0-9a-f]{64})`/)?.[1]
    const actual = createHash('sha256')
      .update(readFileSync(join(PUBLIC_DIR, 'umami.js')))
      .digest('hex')

    expect(recorded).toBeDefined()
    expect(actual).toBe(recorded)
  })
})
