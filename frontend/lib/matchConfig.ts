import type { ApiResult } from './http'
import type { MatchConfig } from './match'

export type UploadLimits = {
  maxCvBytes: number
  minCvTextChars: number
  maxCvTextChars: number
}

// Used until GET /match/config answers, and if it never does.
export const DEFAULT_UPLOAD_LIMITS: UploadLimits = {
  maxCvBytes: 5 * 1024 * 1024,
  minCvTextChars: 50,
  maxCvTextChars: 40_000,
}

function positive(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

export function resolveUploadLimits(result: ApiResult<MatchConfig>): UploadLimits {
  if (!result.ok) return DEFAULT_UPLOAD_LIMITS
  const { max_upload_bytes, cv_text_min_chars, cv_text_max_chars } = result.data
  if (![max_upload_bytes, cv_text_min_chars, cv_text_max_chars].every(positive)) {
    return DEFAULT_UPLOAD_LIMITS
  }
  return {
    maxCvBytes: max_upload_bytes,
    minCvTextChars: cv_text_min_chars,
    maxCvTextChars: cv_text_max_chars,
  }
}
