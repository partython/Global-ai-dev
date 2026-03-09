import type { Metadata } from 'next'
import '@/styles/globals.css'

export const metadata: Metadata = {
  title: 'Partython.ai - AI Sales Team for E-Commerce',
  description: 'AI-powered sales automation platform for e-commerce. Handle customer conversations across WhatsApp, Email, Voice, Instagram and Web Chat. 44,000+ orders processed.',
  icons: {
    icon: [
      {
        url: '/favicon.svg',
        type: 'image/svg+xml',
      },
    ],
  },
  openGraph: {
    title: 'Partython.ai - AI Sales Team for E-Commerce',
    description: 'AI-powered sales automation platform for e-commerce. Handle customer conversations across WhatsApp, Email, Voice, Instagram and Web Chat. 44,000+ orders processed.',
    url: 'https://partython.in',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        {children}
      </body>
    </html>
  )
}
