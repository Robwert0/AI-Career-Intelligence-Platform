// Tab-scoped app state: sessionStorage survives a reload but not closing the tab, and is never
// shared with other tabs. Every key is prefixed, and the whole set belongs to one account.
export const TAB_PREFIX = 'aci:'
const OWNER_KEY = `${TAB_PREFIX}owner`

export type KeyValueStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem' | 'key' | 'length'>

// Private browsing, blocked site data or a server render all make storage unavailable or make
// its accessor throw; recovery is then simply off rather than an error.
export function tabStorage(): KeyValueStore | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage
  } catch {
    return null
  }
}

function attempt(action: () => void): void {
  try {
    action()
  } catch {}
}

export function clearTabSession(store: KeyValueStore | null = tabStorage()): void {
  if (store === null) return
  attempt(() => {
    const keys: string[] = []
    for (let index = 0; index < store.length; index += 1) {
      const key = store.key(index)
      if (key?.startsWith(TAB_PREFIX)) keys.push(key)
    }
    for (const key of keys) store.removeItem(key)
  })
}

// Called whenever a session is established: state left by a different account is wiped before
// anything can read it.
export function claimTabSession(
  accountId: string,
  store: KeyValueStore | null = tabStorage(),
): void {
  if (store === null) return
  attempt(() => {
    const owner = store.getItem(OWNER_KEY)
    if (owner !== null && owner !== accountId) clearTabSession(store)
    store.setItem(OWNER_KEY, accountId)
  })
}

export function readTabItem(
  key: string,
  store: KeyValueStore | null = tabStorage(),
): string | null {
  if (store === null) return null
  try {
    return store.getItem(`${TAB_PREFIX}${key}`)
  } catch {
    return null
  }
}

export function writeTabItem(
  key: string,
  value: string | null,
  store: KeyValueStore | null = tabStorage(),
): void {
  if (store === null) return
  attempt(() =>
    value === null
      ? store.removeItem(`${TAB_PREFIX}${key}`)
      : store.setItem(`${TAB_PREFIX}${key}`, value),
  )
}
