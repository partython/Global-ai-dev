// @ts-nocheck
'use client'

import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import {
  MessageCircle,
  Mail,
  PhoneCall,
  Smartphone,
  Instagram,
  MessageSquare,
  Send,
  Facebook,
  Loader2,
  AlertCircle,
  CheckCircle2,
  XCircle,
  ExternalLink,
  ShoppingBag,
  Radio,
  Globe,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { useAuth } from '@/stores/auth'

// ============================================================================
// Types
// ============================================================================

interface Channel {
  id: string
  name: string
  type: string
  status: 'connected' | 'disconnected' | 'error' | 'active' | 'inactive'
  messageCount: number
  avgResponseTime: number
  lastActivity: string | null
}

interface ChannelStats {
  name: string
  channel: string
  sent: number
  received: number
  avgResponseTime: number
  csat?: number
}

// ============================================================================
// Channel Configuration — OAuth vs Manual vs Auto
// ============================================================================

type AuthType = 'oauth' | 'manual' | 'auto'

interface ChannelConfigEntry {
  icon: React.ReactNode
  color: string
  authType: AuthType
  oauthProvider?: 'meta' | 'shopify' | 'google' | 'microsoft'
  credentials: { key: string; label: string; type: 'text' | 'password' | 'number'; placeholder: string }[]
  description: string
  setupUrl?: string
}

const CHANNEL_CONFIG: Record<string, ChannelConfigEntry> = {
  whatsapp: {
    icon: <MessageCircle className="w-6 h-6" />,
    color: 'bg-green-500',
    authType: 'oauth',
    oauthProvider: 'meta',
    credentials: [],
    description: 'Connect via Meta Business Suite. Authorize your WhatsApp Business Account.',
    setupUrl: 'https://business.facebook.com/settings/whatsapp-business-accounts',
  },
  instagram: {
    icon: <Instagram className="w-6 h-6" />,
    color: 'bg-pink-500',
    authType: 'oauth',
    oauthProvider: 'meta',
    credentials: [],
    description: 'Connect via Meta Business Suite. Authorize your Instagram Business account.',
    setupUrl: 'https://business.facebook.com/settings/instagram-accounts',
  },
  facebook: {
    icon: <Facebook className="w-6 h-6" />,
    color: 'bg-blue-600',
    authType: 'oauth',
    oauthProvider: 'meta',
    credentials: [],
    description: 'Connect via Meta Business Suite. Authorize your Facebook Page for Messenger.',
    setupUrl: 'https://business.facebook.com/settings/pages',
  },
  shopify: {
    icon: <ShoppingBag className="w-6 h-6" />,
    color: 'bg-emerald-600',
    authType: 'oauth',
    oauthProvider: 'shopify',
    credentials: [
      { key: 'shop_domain', label: 'Shopify Store Domain', type: 'text', placeholder: 'yourstore.myshopify.com' },
    ],
    description: 'Connect your Shopify store. We\'ll redirect you to Shopify to authorize access.',
    setupUrl: 'https://admin.shopify.com',
  },
  email: {
    icon: <Mail className="w-6 h-6" />,
    color: 'bg-blue-500',
    authType: 'manual',
    credentials: [
      { key: 'smtp_host', label: 'SMTP Server', type: 'text', placeholder: 'smtp.gmail.com' },
      { key: 'smtp_port', label: 'SMTP Port', type: 'number', placeholder: '587' },
      { key: 'smtp_user', label: 'Email Address', type: 'text', placeholder: 'support@yourdomain.com' },
      { key: 'smtp_password', label: 'App Password', type: 'password', placeholder: 'Your app-specific password' },
    ],
    description: 'Connect your email via SMTP. For Gmail/Outlook, use an App Password.',
  },
  telegram: {
    icon: <Send className="w-6 h-6" />,
    color: 'bg-sky-500',
    authType: 'manual',
    credentials: [
      { key: 'bot_token', label: 'Bot Token', type: 'password', placeholder: '123456789:ABCdefGHIjklMNOpqrsTUVwxyz' },
    ],
    description: 'Create a bot via @BotFather on Telegram, then paste the token here.',
    setupUrl: 'https://t.me/BotFather',
  },
  sms: {
    icon: <Smartphone className="w-6 h-6" />,
    color: 'bg-amber-500',
    authType: 'manual',
    credentials: [
      { key: 'exotel_sid', label: 'Exotel Account SID', type: 'text', placeholder: 'Your Exotel SID' },
      { key: 'exotel_token', label: 'Exotel API Token', type: 'password', placeholder: 'Your Exotel API Token' },
      { key: 'sender_id', label: 'Sender ID', type: 'text', placeholder: 'PRIYAI' },
    ],
    description: 'Connect Exotel for SMS. Get credentials from my.exotel.com.',
    setupUrl: 'https://my.exotel.com/apisettings/site#api-credentials',
  },
  voice: {
    icon: <PhoneCall className="w-6 h-6" />,
    color: 'bg-purple-500',
    authType: 'manual',
    credentials: [
      { key: 'exotel_sid', label: 'Exotel Account SID', type: 'text', placeholder: 'Your Exotel SID' },
      { key: 'exotel_token', label: 'Exotel API Token', type: 'password', placeholder: 'Your Exotel API Token' },
      { key: 'caller_id', label: 'Caller ID / Virtual Number', type: 'text', placeholder: '+91XXXXXXXXXX' },
    ],
    description: 'Connect Exotel for Voice calls. Get credentials from my.exotel.com.',
    setupUrl: 'https://my.exotel.com/apisettings/site#api-credentials',
  },
  webchat: {
    icon: <MessageSquare className="w-6 h-6" />,
    color: 'bg-indigo-500',
    authType: 'auto',
    credentials: [],
    description: 'WebChat is auto-configured. Embed the widget on your website to start.',
  },
  rcs: {
    icon: <Radio className="w-6 h-6" />,
    color: 'bg-teal-500',
    authType: 'manual',
    credentials: [
      { key: 'google_rbm_api_key', label: 'Google RBM API Key', type: 'password', placeholder: 'Your RBM API key' },
      { key: 'google_rbm_project_id', label: 'Google Cloud Project ID', type: 'text', placeholder: 'my-project-123' },
    ],
    description: 'Connect Google RCS Business Messaging. Requires a verified RBM agent.',
    setupUrl: 'https://business.google.com/rcs',
  },
}

// All available channel types (shown in the grid)
const ALL_CHANNELS = [
  { type: 'whatsapp', name: 'WhatsApp Business' },
  { type: 'instagram', name: 'Instagram DM' },
  { type: 'facebook', name: 'Facebook Messenger' },
  { type: 'shopify', name: 'Shopify' },
  { type: 'email', name: 'Email (SMTP)' },
  { type: 'telegram', name: 'Telegram Bot' },
  { type: 'sms', name: 'SMS' },
  { type: 'voice', name: 'Voice / Phone' },
  { type: 'webchat', name: 'Web Chat' },
  { type: 'rcs', name: 'RCS Messaging' },
]

// ============================================================================
// Authenticated API Helper
// ============================================================================

function useAuthenticatedFetch() {
  const token = useAuth((state) => state.token)

  return async (url: string, options: RequestInit = {}) => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const resp = await fetch(url, { ...options, headers })
    return resp
  }
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function ChannelsPage() {
  const [connectedChannels, setConnectedChannels] = useState<Record<string, Channel>>({})
  const [stats, setStats] = useState<ChannelStats[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedChannelType, setSelectedChannelType] = useState<string | null>(null)
  const [showConnectModal, setShowConnectModal] = useState(false)
  const [showShopifyDomainModal, setShowShopifyDomainModal] = useState(false)
  const [shopifyDomain, setShopifyDomain] = useState('')
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  const [testing, setTesting] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [disconnecting, setDisconnecting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ status: string; message: string } | null>(null)
  const [toastMessage, setToastMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const authFetch = useAuthenticatedFetch()
  const searchParams = useSearchParams()

  // Check for OAuth callback results in URL
  useEffect(() => {
    const connected = searchParams.get('connected')
    const status = searchParams.get('status')
    const channels = searchParams.get('channels')

    if (connected && status) {
      if (status === 'success') {
        const channelList = channels ? channels.split(',').join(', ') : connected
        showToast('success', `Successfully connected: ${channelList}`)
      } else if (status === 'denied') {
        showToast('error', `Authorization was denied for ${connected}`)
      } else {
        const reason = searchParams.get('reason') || 'Unknown error'
        showToast('error', `Failed to connect ${connected}: ${reason}`)
      }
      // Clean URL params
      window.history.replaceState({}, '', '/channels')
    }
  }, [searchParams])

  useEffect(() => {
    fetchChannels()
    fetchStats()
  }, [])

  const showToast = (type: 'success' | 'error', text: string) => {
    setToastMessage({ type, text })
    setTimeout(() => setToastMessage(null), 5000)
  }

  // ──────────────────────────────────────────────────────────────
  // API Calls — Real endpoints via /api/channels/*
  // ──────────────────────────────────────────────────────────────

  const fetchChannels = async () => {
    setLoading(true)
    try {
      const resp = await authFetch('/api/channels')
      if (resp.ok) {
        const data = await resp.json()
        const channelMap: Record<string, Channel> = {}
        // data could be an array of {channel, enabled, config, created_at} from channel_router
        const list = Array.isArray(data) ? data : (data.channels || data)
        if (Array.isArray(list)) {
          for (const ch of list) {
            channelMap[ch.channel || ch.type] = {
              id: ch.id || `${ch.channel}_1`,
              name: ALL_CHANNELS.find(c => c.type === (ch.channel || ch.type))?.name || ch.channel,
              type: ch.channel || ch.type,
              status: ch.enabled !== false && ch.status !== 'inactive' ? 'connected' : 'disconnected',
              messageCount: ch.messageCount || 0,
              avgResponseTime: ch.avgResponseTime || 0,
              lastActivity: ch.lastActivity || ch.last_activity || null,
            }
          }
        }
        setConnectedChannels(channelMap)
      }
    } catch (error) {
      console.error('Error fetching channels:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchStats = async () => {
    try {
      const resp = await authFetch('/api/channels/stats')
      if (resp.ok) {
        const data = await resp.json()
        setStats(data.stats || [])
      }
    } catch (error) {
      console.error('Error fetching stats:', error)
    }
  }

  // ──────────────────────────────────────────────────────────────
  // Connect Handler — OAuth redirect OR manual credential modal
  // ──────────────────────────────────────────────────────────────

  const handleConnect = async (channelType: string) => {
    const config = CHANNEL_CONFIG[channelType]
    if (!config) return

    if (config.authType === 'oauth') {
      // OAuth redirect flow
      if (config.oauthProvider === 'meta') {
        // Redirect to Meta (covers WhatsApp, Instagram, Facebook)
        await initiateMetaOAuth()
      } else if (config.oauthProvider === 'shopify') {
        // Need shop domain first, then redirect
        setShowShopifyDomainModal(true)
        return
      } else if (config.oauthProvider === 'google') {
        await initiateGoogleOAuth()
      } else if (config.oauthProvider === 'microsoft') {
        await initiateMicrosoftOAuth()
      }
    } else if (config.authType === 'manual') {
      // Show credential entry modal
      setSelectedChannelType(channelType)
      setCredentials({})
      setTestResult(null)
      setShowConnectModal(true)
    } else if (config.authType === 'auto') {
      // Auto-connect (WebChat)
      await autoConnect(channelType)
    }
  }

  // ──────────────────────────────────────────────────────────────
  // OAuth Initiators — redirect user to platform auth screen
  // ──────────────────────────────────────────────────────────────

  const initiateMetaOAuth = async () => {
    // Meta Embedded Signup — uses Facebook JS SDK inline (no redirect)
    // This connects WhatsApp + Instagram + Facebook in one flow
    try {
      const metaAppId = process.env.NEXT_PUBLIC_META_APP_ID
      const configId = process.env.NEXT_PUBLIC_META_CONFIG_ID

      if (!metaAppId) {
        showToast('error', 'Meta App not configured. Add NEXT_PUBLIC_META_APP_ID to environment.')
        return
      }

      // Load Facebook SDK if not already loaded
      if (!(window as any).FB) {
        await new Promise<void>((resolve) => {
          const script = document.createElement('script')
          script.src = 'https://connect.facebook.net/en_US/sdk.js'
          script.async = true
          script.defer = true
          script.crossOrigin = 'anonymous'
          script.onload = () => {
            ;(window as any).FB.init({
              appId: metaAppId,
              cookie: true,
              xfbml: true,
              version: 'v18.0',
            })
            resolve()
          }
          document.body.appendChild(script)
        })
      }

      // Meta Embedded Signup with FB.login()
      ;(window as any).FB.login(
        async (response: any) => {
          if (response.authResponse) {
            const code = response.authResponse.code
            showToast('info', 'Connecting your Meta accounts...')

            try {
              // Exchange code via our backend
              const res = await authFetch('/api/v1/whatsapp/embedded-signup', {
                method: 'POST',
                body: JSON.stringify({
                  code,
                  config_id: configId,
                  permissions: response.authResponse.grantedScopes?.split(',') || [],
                }),
              })

              const data = await res.json()

              if (res.ok) {
                showToast('success',
                  `Connected ${data.channels_connected?.join(', ')}! ` +
                  (data.calling_enabled ? 'WhatsApp Business Calling enabled.' : '')
                )
                fetchChannels() // Refresh channel list
              } else {
                showToast('error', data.detail || 'Failed to complete Meta signup')
              }
            } catch (err) {
              console.error('Embedded signup backend error:', err)
              showToast('error', 'Failed to connect Meta accounts')
            }
          } else {
            showToast('error', 'Meta authorization was cancelled')
          }
        },
        {
          // Meta Embedded Signup config
          config_id: configId,
          response_type: 'code',
          override_default_response_type: true,
          extras: {
            setup: {
              // Embedded Signup specific: request WhatsApp + Instagram + Messenger
              feature: 'whatsapp_embedded_signup',
              sessionInfoVersion: 2,
            },
          },
          scope: [
            'whatsapp_business_management',
            'whatsapp_business_messaging',
            'business_management',
            'pages_messaging',
            'pages_manage_metadata',
            'instagram_basic',
            'instagram_manage_messages',
          ].join(','),
        }
      )
    } catch (error) {
      console.error('Meta Embedded Signup error:', error)
      showToast('error', 'Failed to initiate Meta Embedded Signup')
    }
  }

  const initiateShopifyOAuth = async () => {
    if (!shopifyDomain) {
      showToast('error', 'Please enter your Shopify store domain')
      return
    }

    try {
      const resp = await authFetch('/api/oauth/shopify', {
        method: 'POST',
        body: JSON.stringify({ shop_domain: shopifyDomain }),
      })
      const data = await resp.json()

      if (data.auth_url) {
        // Store state + shop in sessionStorage (not cookies — survives redirect reliably)
        sessionStorage.setItem('shopify_oauth_state', data.state)
        sessionStorage.setItem('shopify_oauth_shop', data.shop_domain)

        setShowShopifyDomainModal(false)
        window.location.href = data.auth_url
      } else {
        showToast('error', data.message || 'Failed to generate Shopify authorization URL')
      }
    } catch (error) {
      console.error('Shopify OAuth error:', error)
      showToast('error', 'Failed to initiate Shopify OAuth')
    }
  }

  const initiateGoogleOAuth = async () => {
    try {
      const resp = await authFetch('/api/oauth/google', { method: 'POST' })
      const data = await resp.json()
      if (data.auth_url) {
        window.location.href = data.auth_url
      } else {
        showToast('error', data.message || 'Google OAuth not configured')
      }
    } catch (error) {
      showToast('error', 'Failed to initiate Google OAuth')
    }
  }

  const initiateMicrosoftOAuth = async () => {
    try {
      const resp = await authFetch('/api/oauth/microsoft', { method: 'POST' })
      const data = await resp.json()
      if (data.auth_url) {
        window.location.href = data.auth_url
      } else {
        showToast('error', data.message || 'Microsoft OAuth not configured')
      }
    } catch (error) {
      showToast('error', 'Failed to initiate Microsoft OAuth')
    }
  }

  // ──────────────────────────────────────────────────────────────
  // Manual Credential Handlers
  // ──────────────────────────────────────────────────────────────

  const handleTestConnection = async () => {
    if (!selectedChannelType) return
    setTesting(true)
    setTestResult(null)
    try {
      const resp = await authFetch('/api/channels/test', {
        method: 'POST',
        body: JSON.stringify({
          channel: selectedChannelType,
          credentials: credentials,
        }),
      })
      const data = await resp.json()
      setTestResult(data)
    } catch (error) {
      setTestResult({ status: 'failed', message: 'Connection test failed. Check your credentials.' })
    } finally {
      setTesting(false)
    }
  }

  const handleSaveConnection = async () => {
    if (!selectedChannelType) return
    setConnecting(true)
    try {
      const resp = await authFetch('/api/channels', {
        method: 'POST',
        body: JSON.stringify({
          channel: selectedChannelType,
          credentials: credentials,
        }),
      })
      if (resp.ok) {
        setShowConnectModal(false)
        showToast('success', `${CHANNEL_CONFIG[selectedChannelType]?.description?.split('.')[0] || selectedChannelType} connected!`)
        await fetchChannels()
        await fetchStats()
      } else {
        const data = await resp.json()
        showToast('error', data.message || 'Failed to connect channel')
      }
    } catch (error) {
      showToast('error', 'Failed to save connection')
    } finally {
      setConnecting(false)
    }
  }

  const autoConnect = async (channelType: string) => {
    try {
      const resp = await authFetch('/api/channels', {
        method: 'POST',
        body: JSON.stringify({ channel: channelType, credentials: {} }),
      })
      if (resp.ok) {
        showToast('success', 'WebChat widget configured! Embed it on your site.')
        await fetchChannels()
      }
    } catch (error) {
      showToast('error', 'Failed to configure WebChat')
    }
  }

  const handleDisconnect = async (channelType: string) => {
    setDisconnecting(channelType)
    try {
      const resp = await authFetch(`/api/channels?channel=${encodeURIComponent(channelType)}`, {
        method: 'DELETE',
      })
      if (resp.ok) {
        showToast('success', `${channelType} disconnected`)
        await fetchChannels()
        await fetchStats()
      } else {
        showToast('error', 'Failed to disconnect channel')
      }
    } catch (error) {
      showToast('error', 'Failed to disconnect channel')
    } finally {
      setDisconnecting(null)
    }
  }

  // ──────────────────────────────────────────────────────────────
  // UI Helpers
  // ──────────────────────────────────────────────────────────────

  const getChannelStatus = (type: string): 'connected' | 'disconnected' | 'error' => {
    const ch = connectedChannels[type]
    if (!ch) return 'disconnected'
    if (ch.status === 'active' || ch.status === 'connected') return 'connected'
    if (ch.status === 'error') return 'error'
    return 'disconnected'
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'connected':
        return (
          <Badge className="bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" />
            Connected
          </Badge>
        )
      case 'disconnected':
        return (
          <Badge className="bg-gray-500/20 text-gray-700 dark:text-gray-400 border-gray-500/30 flex items-center gap-1">
            <XCircle className="w-3 h-3" />
            Not Connected
          </Badge>
        )
      case 'error':
        return (
          <Badge className="bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" />
            Error
          </Badge>
        )
    }
  }

  const getAuthTypeBadge = (authType: AuthType) => {
    switch (authType) {
      case 'oauth':
        return (
          <span className="text-[10px] font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/30 px-1.5 py-0.5 rounded">
            OAuth
          </span>
        )
      case 'manual':
        return (
          <span className="text-[10px] font-medium text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 px-1.5 py-0.5 rounded">
            API Key
          </span>
        )
      case 'auto':
        return (
          <span className="text-[10px] font-medium text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 px-1.5 py-0.5 rounded">
            Auto
          </span>
        )
    }
  }

  // ──────────────────────────────────────────────────────────────
  // Render
  // ──────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-950 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Toast Notification */}
        <AnimatePresence>
          {toastMessage && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className={`fixed top-20 right-8 z-50 px-6 py-4 rounded-xl shadow-lg flex items-center gap-3 ${
                toastMessage.type === 'success'
                  ? 'bg-green-600 text-white'
                  : 'bg-red-600 text-white'
              }`}
            >
              {toastMessage.type === 'success' ? (
                <CheckCircle2 className="w-5 h-5" />
              ) : (
                <AlertCircle className="w-5 h-5" />
              )}
              <span className="font-medium text-sm">{toastMessage.text}</span>
              <button onClick={() => setToastMessage(null)} className="ml-2 opacity-70 hover:opacity-100">
                <XCircle className="w-4 h-4" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-12"
        >
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
            Channels
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Connect your communication channels. OAuth channels redirect you to the platform to authorize securely.
          </p>
        </motion.div>

        {/* Channel Grid */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 mb-12"
        >
          {loading ? (
            Array.from({ length: 10 }).map((_, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <Card className="h-64 bg-gray-200 dark:bg-gray-800 animate-pulse" />
              </motion.div>
            ))
          ) : (
            ALL_CHANNELS.map((ch, index) => {
              const config = CHANNEL_CONFIG[ch.type]
              const status = getChannelStatus(ch.type)
              const channelData = connectedChannels[ch.type]
              if (!config) return null

              return (
                <motion.div
                  key={ch.type}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.04 }}
                  whileHover={{ y: -4 }}
                >
                  <Card className="h-full p-6 flex flex-col justify-between hover:shadow-lg dark:hover:shadow-lg/20 transition-all border border-gray-200 dark:border-gray-700">
                    {/* Top */}
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <div className={`${config.color} p-3 rounded-lg text-white`}>
                          {config.icon}
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          {getStatusBadge(status)}
                          {getAuthTypeBadge(config.authType)}
                        </div>
                      </div>

                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
                        {ch.name}
                      </h3>
                      <p className="text-xs text-gray-500 dark:text-gray-500 mb-4 leading-relaxed">
                        {config.description}
                      </p>

                      {/* Stats (if connected) */}
                      {status === 'connected' && channelData && (
                        <div className="space-y-1.5 mb-4">
                          {channelData.messageCount > 0 && (
                            <div className="flex justify-between text-sm">
                              <span className="text-gray-500 dark:text-gray-400">Messages</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {channelData.messageCount.toLocaleString()}
                              </span>
                            </div>
                          )}
                          {channelData.avgResponseTime > 0 && (
                            <div className="flex justify-between text-sm">
                              <span className="text-gray-500 dark:text-gray-400">Avg Response</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {channelData.avgResponseTime}s
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2 pt-4 border-t border-gray-200 dark:border-gray-700">
                      {status === 'connected' ? (
                        <>
                          <Button variant="outline" size="sm" className="flex-1 text-xs">
                            Manage
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="flex-1 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950"
                            onClick={() => handleDisconnect(ch.type)}
                            disabled={disconnecting === ch.type}
                          >
                            {disconnecting === ch.type ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              'Disconnect'
                            )}
                          </Button>
                        </>
                      ) : (
                        <Button
                          size="sm"
                          className="flex-1 text-xs bg-blue-600 hover:bg-blue-700 text-white flex items-center justify-center gap-1.5"
                          onClick={() => handleConnect(ch.type)}
                        >
                          {config.authType === 'oauth' && <ExternalLink className="w-3 h-3" />}
                          {config.authType === 'oauth' ? 'Connect with OAuth' : config.authType === 'auto' ? 'Enable' : 'Connect'}
                        </Button>
                      )}
                    </div>
                  </Card>
                </motion.div>
              )
            })
          )}
        </motion.div>

        {/* Stats Section */}
        {stats.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Card className="p-8 border border-gray-200 dark:border-gray-700">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-8">
                Channel Analytics
              </h2>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                    Messages (Sent/Received)
                  </h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={stats}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="name" stroke="#6b7280" />
                      <YAxis stroke="#6b7280" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2937',
                          border: '1px solid #374151',
                          borderRadius: '0.5rem',
                          color: '#fff',
                        }}
                      />
                      <Legend />
                      <Bar dataKey="sent" fill="#3b82f6" />
                      <Bar dataKey="received" fill="#10b981" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                    Response Time (seconds)
                  </h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={stats}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="name" stroke="#6b7280" />
                      <YAxis stroke="#6b7280" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2937',
                          border: '1px solid #374151',
                          borderRadius: '0.5rem',
                          color: '#fff',
                        }}
                      />
                      <Bar dataKey="avgResponseTime" fill="#f59e0b" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </div>

      {/* ────────────────────────────────────────────────── */}
      {/* Manual Credential Connect Modal                    */}
      {/* ────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showConnectModal && selectedChannelType && (
          <Modal
            isOpen={showConnectModal}
            onClose={() => setShowConnectModal(false)}
            title={`Connect ${ALL_CHANNELS.find(c => c.type === selectedChannelType)?.name || selectedChannelType}`}
          >
            <div className="space-y-6">
              {/* Setup Link */}
              {CHANNEL_CONFIG[selectedChannelType]?.setupUrl && (
                <a
                  href={CHANNEL_CONFIG[selectedChannelType].setupUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  <ExternalLink className="w-4 h-4" />
                  Open {ALL_CHANNELS.find(c => c.type === selectedChannelType)?.name} setup page
                </a>
              )}

              {/* Credential Fields */}
              <div className="space-y-4">
                {CHANNEL_CONFIG[selectedChannelType]?.credentials.map((field) => (
                  <div key={field.key}>
                    <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">
                      {field.label}
                    </label>
                    <Input
                      type={field.type}
                      placeholder={field.placeholder}
                      value={credentials[field.key] || ''}
                      onChange={(e) =>
                        setCredentials({ ...credentials, [field.key]: e.target.value })
                      }
                      className="w-full"
                    />
                  </div>
                ))}
              </div>

              {/* Test Result */}
              {testResult && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`p-4 rounded-lg flex items-center gap-2 ${
                    testResult.status === 'success'
                      ? 'bg-green-500/20 text-green-700 dark:text-green-400 border border-green-500/30'
                      : 'bg-red-500/20 text-red-700 dark:text-red-400 border border-red-500/30'
                  }`}
                >
                  {testResult.status === 'success' ? (
                    <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
                  ) : (
                    <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  )}
                  <span className="font-medium text-sm">{testResult.message}</span>
                </motion.div>
              )}

              {/* Buttons */}
              <div className="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <Button
                  variant="outline"
                  onClick={() => setShowConnectModal(false)}
                  disabled={testing || connecting}
                  className="flex-1"
                >
                  Cancel
                </Button>
                <Button
                  variant="outline"
                  onClick={handleTestConnection}
                  disabled={testing || connecting}
                  className="flex-1"
                >
                  {testing ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Testing...
                    </span>
                  ) : (
                    'Test Connection'
                  )}
                </Button>
                <Button
                  onClick={handleSaveConnection}
                  disabled={connecting || testResult?.status !== 'success'}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
                >
                  {connecting ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Saving...
                    </span>
                  ) : (
                    'Save & Connect'
                  )}
                </Button>
              </div>
            </div>
          </Modal>
        )}
      </AnimatePresence>

      {/* ────────────────────────────────────────────────── */}
      {/* Shopify Domain Modal (before OAuth redirect)       */}
      {/* ────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showShopifyDomainModal && (
          <Modal
            isOpen={showShopifyDomainModal}
            onClose={() => setShowShopifyDomainModal(false)}
            title="Connect Shopify Store"
          >
            <div className="space-y-6">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Enter your Shopify store domain. You'll be redirected to Shopify to authorize access.
              </p>
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-white mb-2">
                  Store Domain
                </label>
                <Input
                  type="text"
                  placeholder="yourstore.myshopify.com"
                  value={shopifyDomain}
                  onChange={(e) => setShopifyDomain(e.target.value)}
                  className="w-full"
                />
              </div>
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={() => setShowShopifyDomainModal(false)}
                  className="flex-1"
                >
                  Cancel
                </Button>
                <Button
                  onClick={initiateShopifyOAuth}
                  className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white flex items-center justify-center gap-2"
                >
                  <ExternalLink className="w-4 h-4" />
                  Continue to Shopify
                </Button>
              </div>
            </div>
          </Modal>
        )}
      </AnimatePresence>
    </div>
  )
}
