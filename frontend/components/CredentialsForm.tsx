'use client'

import { useState } from 'react'
import type { ApiResult } from '@/lib/http'
import { authErrorMessage } from '@/lib/messages'

type CredentialsFormProps = {
  submitLabel: string
  passwordHint?: string
  autoCompletePassword: 'current-password' | 'new-password'
  onSubmit: (email: string, password: string) => Promise<ApiResult<unknown>>
  onSuccess: () => void
}

const FIELD_CLASS =
  'border border-line bg-transparent px-3 py-2 text-sm outline-none focus-visible:border-accent'

export function CredentialsForm({
  submitLabel,
  passwordHint,
  autoCompletePassword,
  onSubmit,
  onSuccess,
}: CredentialsFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)

    const result = await onSubmit(email, password)

    setPending(false)
    if (result.ok) onSuccess()
    else setError(authErrorMessage(result))
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <label className="flex flex-col gap-2">
        <span className="font-mono text-xs text-muted">email</span>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
          autoFocus
          className={FIELD_CLASS}
        />
      </label>

      <label className="flex flex-col gap-2">
        <span className="font-mono text-xs text-muted">password</span>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          minLength={8}
          autoComplete={autoCompletePassword}
          className={FIELD_CLASS}
        />
        {passwordHint ? <span className="font-mono text-xs text-muted">{passwordHint}</span> : null}
      </label>

      <p role="alert" aria-live="polite" className="min-h-5 font-mono text-xs text-danger">
        {error}
      </p>

      <button
        type="submit"
        disabled={pending}
        className="border border-fg px-3 py-2 font-mono text-sm transition-opacity disabled:opacity-40"
      >
        {pending ? 'working…' : submitLabel}
      </button>
    </form>
  )
}
