import { useEffect, useState } from 'react'
import { getMatchConfig } from './match'
import { DEFAULT_UPLOAD_LIMITS, resolveUploadLimits, type UploadLimits } from './matchConfig'

export function useMatchConfig(): UploadLimits {
  const [limits, setLimits] = useState<UploadLimits>(DEFAULT_UPLOAD_LIMITS)

  useEffect(() => {
    let active = true
    void getMatchConfig().then((result) => {
      if (active) setLimits(resolveUploadLimits(result))
    })
    return () => {
      active = false
    }
  }, [])

  return limits
}
