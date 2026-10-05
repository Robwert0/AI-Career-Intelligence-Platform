import type { Metadata } from 'next'
import { AdminView } from '@/components/admin/AdminView'
import { RequireAuth } from '@/components/RequireAuth'

export const metadata: Metadata = { title: 'Admin', robots: { index: false, follow: false } }

export default function AdminPage() {
  return (
    <RequireAuth>
      <AdminView />
    </RequireAuth>
  )
}
