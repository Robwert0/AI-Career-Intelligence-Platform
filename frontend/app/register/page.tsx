'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/AuthProvider'
import { CredentialsForm } from '@/components/CredentialsForm'

export default function RegisterPage() {
  const { signUp } = useAuth()
  const router = useRouter()

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-8 px-4 py-16">
      <div className="space-y-2">
        <h1 className="font-mono text-sm">create an account</h1>
        <p className="text-sm text-muted">You will sign in on the next step.</p>
      </div>

      <CredentialsForm
        submitLabel="create account"
        passwordHint="at least 8 characters"
        autoCompletePassword="new-password"
        onSubmit={signUp}
        onSuccess={() => router.push('/login?registered=1')}
      />

      <p className="font-mono text-xs text-muted">
        already have one?{' '}
        <Link href="/login" className="text-accent underline underline-offset-4">
          sign in
        </Link>
      </p>
    </main>
  )
}
