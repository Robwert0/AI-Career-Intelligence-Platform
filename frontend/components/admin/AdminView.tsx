'use client'

import { notFound } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { type AdminUserRow, type AdminUsersPage, formatWhen, listUsers } from '@/lib/admin'
import { authErrorMessage } from '@/lib/messages'
import { ROLE_OPTIONS, roleLabel } from '@/lib/roles'

const DASHBOARD_URL = process.env.NEXT_PUBLIC_UMAMI_DASHBOARD_URL

type State =
  | { kind: 'loading' }
  | { kind: 'missing' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; page: AdminUsersPage; rows: AdminUserRow[] }

export function AdminView() {
  const { sessionExpired } = useAuth()
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    let active = true
    listUsers(0).then((result) => {
      if (!active) return
      if (result.ok) setState({ kind: 'ready', page: result.data, rows: result.data.items })
      else if (result.status === 404) setState({ kind: 'missing' })
      else if (result.status === 401) sessionExpired()
      else setState({ kind: 'error', message: authErrorMessage(result) })
    })
    return () => {
      active = false
    }
  }, [sessionExpired])

  if (state.kind === 'missing') notFound()

  async function loadMore() {
    if (state.kind !== 'ready' || loadingMore) return
    setLoadingMore(true)
    const result = await listUsers(state.rows.length)
    setLoadingMore(false)
    if (result.ok) {
      setState({ kind: 'ready', page: result.data, rows: [...state.rows, ...result.data.items] })
    } else {
      setState({ kind: 'error', message: authErrorMessage(result) })
    }
  }

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 space-y-8 px-4 py-12">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-mono text-sm">admin · who viewed the cv</h1>
        {DASHBOARD_URL ? (
          <a
            href={DASHBOARD_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono text-xs text-accent underline underline-offset-4"
          >
            Visitor analytics →
          </a>
        ) : null}
      </div>

      {state.kind === 'loading' ? <p className="font-mono text-xs text-muted">loading…</p> : null}
      {state.kind === 'error' ? (
        <p role="alert" className="font-mono text-xs text-danger">
          {state.message}
        </p>
      ) : null}

      {state.kind === 'ready' ? (
        <>
          <dl className="grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="accounts" value={state.page.total} />
            {ROLE_OPTIONS.map((option) => (
              <Stat
                key={option.value}
                label={option.label}
                value={state.page.by_role[option.value]}
              />
            ))}
            <Stat label="unspecified" value={state.page.by_role.unspecified} />
          </dl>

          <div className="overflow-x-auto border border-line">
            <table className="w-full text-left text-sm">
              <thead className="font-mono text-xs text-muted">
                <tr>
                  {['email', 'company', 'role', 'signed up', 'last active'].map((heading) => (
                    <th key={heading} scope="col" className="px-3 py-2 font-normal">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {state.rows.map((row) => (
                  <tr key={row.id} className="border-t border-line">
                    <td className="px-3 py-2">{row.email}</td>
                    <td className="px-3 py-2">{row.company ?? '—'}</td>
                    <td className="px-3 py-2">{roleLabel(row.role)}</td>
                    <td className="whitespace-nowrap px-3 py-2">{formatWhen(row.created_at)}</td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {formatWhen(row.last_active_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {state.rows.length < state.page.total ? (
            <button
              type="button"
              onClick={loadMore}
              disabled={loadingMore}
              className="border border-fg px-3 py-2 font-mono text-sm disabled:opacity-40"
            >
              {loadingMore ? 'loading…' : 'load more'}
            </button>
          ) : null}
        </>
      ) : null}
    </main>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-bg px-4 py-3">
      <dt className="font-mono text-xs text-muted">{label}</dt>
      <dd className="text-2xl">{value}</dd>
    </div>
  )
}
