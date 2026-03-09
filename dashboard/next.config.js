/** @type {import('next').NextConfig} */

const isDev = process.env.NODE_ENV !== 'production'

const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  swcMinify: true,
  images: {
    // SECURITY: Whitelist specific image domains only — no wildcards
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'api.dicebear.com',
      },
      {
        protocol: 'https',
        hostname: '*.cloudfront.net',
      },
      {
        protocol: 'https',
        hostname: 'avatars.githubusercontent.com',
      },
    ],
    // Unoptimized for Vercel hobby plan (avoids image optimization quota)
    unoptimized: process.env.VERCEL_ENV === 'preview' || false,
  },
  headers: async () => {
    // SECURITY: Origin whitelist from environment, fallback to Vercel auto-URLs
    const allowedOrigins = process.env.ALLOWED_ORIGINS
      || (process.env.VERCEL_URL
        ? `https://${process.env.VERCEL_URL}`
        : 'http://localhost:3000')

    // Gateway URL for API calls (backend microservices)
    const gatewayUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9000'

    // Allow connections to gateway URL in all environments
    // In development/docker, also allow localhost wildcards + WebSocket
    const connectSrc = isDev
      ? `'self' http://localhost:* ws://localhost:* ${gatewayUrl} ${allowedOrigins}`
      : `'self' https://*.vercel.app http://localhost:* ws://localhost:* ${gatewayUrl} ${allowedOrigins}`

    return [
      {
        source: '/api/:path*',
        headers: [
          { key: 'Access-Control-Allow-Credentials', value: 'true' },
          { key: 'Access-Control-Allow-Origin', value: allowedOrigins.split(',')[0] },
          { key: 'Access-Control-Allow-Methods', value: 'GET,OPTIONS,PATCH,DELETE,POST,PUT' },
          {
            key: 'Access-Control-Allow-Headers',
            value: 'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, Authorization',
          },
        ],
      },
      // SECURITY: Harden all routes with security headers
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-XSS-Protection', value: '1; mode=block' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: https:",
              "font-src 'self' data:",
              `connect-src ${connectSrc}`,
            ].join('; '),
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload',
          },
        ],
      },
    ]
  },
}

module.exports = nextConfig
