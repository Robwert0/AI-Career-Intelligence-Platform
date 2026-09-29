import { useCallback, useEffect, useRef } from 'react'

// Focus must wait for the commit: the element to focus is often the one the update creates.
export function useFocusAfterRender(): (id: string) => void {
  const pending = useRef<string | null>(null)

  useEffect(() => {
    if (pending.current === null) return
    document.getElementById(pending.current)?.focus()
    pending.current = null
  })

  return useCallback((id: string) => {
    pending.current = id
  }, [])
}
