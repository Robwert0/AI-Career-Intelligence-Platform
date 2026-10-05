'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { CredentialsForm, FIELD_CLASS } from '@/components/CredentialsForm'
import { ROLE_OPTIONS, type UserRole } from '@/lib/roles'
import { safeNextPath, withNext } from '@/lib/redirect'

function RegisterForm() {
  const { signUp } = useAuth()
  const router = useRouter()
  const next = safeNextPath(useSearchParams().get('next'))
  const [company, setCompany] = useState('')
  const [role, setRole] = useState<UserRole | ''>('')

  return (
    <>
      <div className="space-y-2">
        <h1 className="font-mono text-sm">create an account</h1>
        <p className="text-sm text-muted">You will sign in on the next step.</p>
      </div>

      <CredentialsForm
        submitLabel="create account"
        passwordHint="at least 8 characters"
        autoCompletePassword="new-password"
        onSubmit={(email, password) =>
          signUp(email, password, { company, role: role || undefined })
        }
        onSuccess={() => router.push(withNext('/login?registered=1', next))}
      >
        <label className="flex flex-col gap-2">
          <span className="font-mono text-xs text-muted">company (optional)</span>
          <input
            type="text"
            value={company}
            onChange={(event) => setCompany(event.target.value)}
            maxLength={100}
            autoComplete="organization"
            className={FIELD_CLASS}
          />
        </label>

        <label className="flex flex-col gap-2">
          <span className="font-mono text-xs text-muted">i am a… (optional)</span>
          <select
            value={role}
            onChange={(event) => setRole(event.target.value as UserRole | '')}
            className={FIELD_CLASS.replace('bg-transparent', 'bg-bg')}
          >
            <option value="">prefer not to say</option>
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <p className="font-mono text-xs text-muted">
          Your email, company, role, sign-up date and last visit are visible to Robert.
        </p>
      </CredentialsForm>

      <p className="font-mono text-xs text-muted">
        already have one?{' '}
        <Link href={withNext('/login', next)} className="text-accent underline underline-offset-4">
          sign in
        </Link>
      </p>
    </>
  )
}

export default function RegisterPage() {
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-8 px-4 py-16">
      <Suspense fallback={null}>
        <RegisterForm />
      </Suspense>
    </main>
  )
}
