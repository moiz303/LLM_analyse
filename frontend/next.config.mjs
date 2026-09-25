/** @type {import('next').NextConfig} */
const backendUrl = process.env.BACKEND_URL || process.env.API_URL || 'http://localhost:8000'

const nextConfig = {
  async rewrites() {
    return [{
      source: '/backend/:path*',
      destination: `${backendUrl}/:path*`,
    }]
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
