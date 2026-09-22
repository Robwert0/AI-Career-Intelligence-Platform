import type { NextConfig } from 'next'

const backendOrigin = process.env.BACKEND_ORIGIN ?? 'http://localhost:8000'

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${backendOrigin}/:path*` }]
  },
}

export default nextConfig
