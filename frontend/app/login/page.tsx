'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { CredentialsForm } from '@/components/CredentialsForm'

function LoginForm() {
  const { signIn } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const justRegistered = params.get('registered') === '1'
  const logoutIncomplete = params.get('logout') === 'incomplete'
  const sessionExpired = params.get('session') === 'expired'

  return (
    <>
      <div className="space-y-2">
        <h1 className="font-mono text-sm">sign in</h1>
        {justRegistered ? (
          <p className="font-mono text-xs text-accent">account created — sign in to continue</p>
        ) : (
          <p className="text-sm text-muted">Ask questions about the CV.</p>
        )}
      </div>

      {sessionExpired ? (
        <p role="alert" className="border border-line px-3 py-2 font-mono text-xs text-muted">
          Your session ended. Sign in again to continue.
        </p>
      ) : null}

      {logoutIncomplete ? (
        <p role="alert" className="border border-danger px-3 py-2 font-mono text-xs text-danger">
          Signed out on this device, but the session could not be ended on the server. Sign in and
          out again once the connection is back.
        </p>
      ) : null}

      <CredentialsForm
        submitLabel="sign in"
        autoCompletePassword="current-password"
        onSubmit={signIn}
        onSuccess={() => router.replace('/chat')}
      />

      <p className="font-mono text-xs text-muted">
        no account?{' '}
        <Link href="/register" className="text-accent underline underline-offset-4">
          create one
        </Link>
      </p>
    </>
  )
}

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-8 px-4 py-16">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  )
}
