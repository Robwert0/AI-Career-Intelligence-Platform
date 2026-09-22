'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { CredentialsForm } from '@/components/CredentialsForm'

function LoginForm() {
  const { signIn } = useAuth()
  const router = useRouter()
  const justRegistered = useSearchParams().get('registered') === '1'

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

      <CredentialsForm
        submitLabel="sign in"
        autoCompletePassword="current-password"
        onSubmit={signIn}
        onSuccess={() => router.push('/chat')}
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
