import type { NextConfig } from 'next'

const backendOrigin = process.env.BACKEND_ORIGIN ?? 'http://localhost:8000'

if (process.env.NODE_ENV === 'production' && !process.env.BACKEND_ORIGIN) {
  throw new Error('BACKEND_ORIGIN must be set in production')
}

const PROXIED_PREFIXES = ['auth', 'users', 'chat']

const isDevelopment = process.env.NODE_ENV !== 'production'

// React needs eval() for dev-only debugging features and never uses it in production, so the
// relaxation is dev-only. The strict production policy is the one verified against `next build`.
const scriptSrc = isDevelopment
  ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
  : "script-src 'self' 'unsafe-inline'"

const SECURITY_HEADERS = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'X-Frame-Options', value: 'DENY' },
  {
    key: 'Content-Security-Policy',
    value: [
      "default-src 'self'",
      scriptSrc,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self' data:",
      "connect-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'none'",
      "form-action 'self'",
      "object-src 'none'",
    ].join('; '),
  },
]

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      ...PROXIED_PREFIXES.map((prefix) => ({
        source: `/api/${prefix}/:path*`,
        destination: `${backendOrigin}/${prefix}/:path*`,
      })),
      { source: '/api/chat', destination: `${backendOrigin}/chat` },
    ]
  },
  async headers() {
    return [{ source: '/:path*', headers: SECURITY_HEADERS }]
  },
}

export default nextConfig
