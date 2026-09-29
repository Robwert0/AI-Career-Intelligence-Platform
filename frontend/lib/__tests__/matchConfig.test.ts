import { describe, expect, it } from 'vitest'
import { DEFAULT_UPLOAD_LIMITS, resolveUploadLimits } from '../matchConfig'

describe('resolveUploadLimits', () => {
  it('uses the server limits when the fetch succeeded', () => {
    expect(
      resolveUploadLimits({
        ok: true,
        data: { max_upload_bytes: 2_097_152, cv_text_min_chars: 80, cv_text_max_chars: 10_000 },
      }),
    ).toEqual({ maxCvBytes: 2_097_152, minCvTextChars: 80, maxCvTextChars: 10_000 })
  })

  it('falls back to 5 MB and the default text bounds when the fetch failed', () => {
    const limits = resolveUploadLimits({ ok: false, status: 503, detail: 'x' })

    expect(limits).toBe(DEFAULT_UPLOAD_LIMITS)
    expect(limits.maxCvBytes).toBe(5 * 1024 * 1024)
  })

  it('falls back when the server sends nonsense', () => {
    const bad = { max_upload_bytes: 0, cv_text_min_chars: 50, cv_text_max_chars: 40_000 }

    expect(resolveUploadLimits({ ok: true, data: bad })).toBe(DEFAULT_UPLOAD_LIMITS)
  })
})
