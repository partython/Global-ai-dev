// @ts-nocheck
'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  CreditCard,
  Download,
  TrendingUp,
  AlertCircle,
  Check,
  ArrowUpRight,
  RefreshCw,
  AlertTriangle,
  FileText,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

// Types
interface Subscription {
  plan: string
  billingCycle: string
  currentAmount: number
  nextBillingDate: string
  status: string
  startDate: string
  features: string[]
}

interface UsageMetric {
  used: number
  limit: number
  unit: string
}

interface UsageData {
  messages: UsageMetric
  apiCalls: UsageMetric
  storage: UsageMetric
  agents: UsageMetric
}

interface UsageHistory {
  date: string
  messages: number
  apiCalls: number
  tokens: number
}

interface Invoice {
  id: string
  date: string
  amount: number
  status: string
  pdfUrl: string
}

interface PaymentMethod {
  id: string
  type: string
  lastFour: string
  expiry: string
  isDefault: boolean
  holderName: string
}

interface PricingPlan {
  name: string
  price: number
  color: string
  description: string
  features: string[]
  recommended: boolean
}

// Mock Data
const mockCurrentSubscription: Subscription = {
  plan: 'growth',
  billingCycle: 'monthly',
  currentAmount: 149,
  nextBillingDate: '2026-04-07',
  status: 'active',
  startDate: '2025-10-07',
  features: ['100k messages/month', 'API access', 'Custom integrations', '24/7 support'],
}

const mockUsageData: UsageData = {
  messages: { used: 4523, limit: 10000, unit: 'messages' },
  apiCalls: { used: 1254, limit: 50000, unit: 'calls' },
  storage: { used: 24.5, limit: 100, unit: 'GB' },
  agents: { used: 2, limit: 5, unit: 'agents' },
}

const mockUsageHistory: UsageHistory[] = [
  { date: 'Mar 1', messages: 1450, apiCalls: 420, tokens: 42300 },
  { date: 'Mar 2', messages: 1680, apiCalls: 510, tokens: 48900 },
  { date: 'Mar 3', messages: 1290, apiCalls: 380, tokens: 39500 },
  { date: 'Mar 4', messages: 2100, apiCalls: 650, tokens: 61200 },
  { date: 'Mar 5', messages: 1840, apiCalls: 520, tokens: 52100 },
  { date: 'Mar 6', messages: 1950, apiCalls: 580, tokens: 55800 },
  { date: 'Mar 7', messages: 2340, apiCalls: 720, tokens: 67500 },
]

const mockInvoices: Invoice[] = [
  { id: 'INV-2026-003', date: '2026-03-07', amount: 149.0, status: 'paid', pdfUrl: '/invoices/2026-003.pdf' },
  { id: 'INV-2026-002', date: '2026-02-07', amount: 149.0, status: 'paid', pdfUrl: '/invoices/2026-002.pdf' },
  { id: 'INV-2026-001', date: '2026-01-07', amount: 149.0, status: 'paid', pdfUrl: '/invoices/2026-001.pdf' },
  { id: 'INV-2025-012', date: '2025-12-07', amount: 99.0, status: 'paid', pdfUrl: '/invoices/2025-012.pdf' },
  { id: 'INV-2025-011', date: '2025-11-07', amount: 99.0, status: 'paid', pdfUrl: '/invoices/2025-011.pdf' },
]

const mockPaymentMethods: PaymentMethod[] = [
  { id: '1', type: 'visa', lastFour: '4242', expiry: '12/26', isDefault: true, holderName: 'Priya Sharma' },
  { id: '2', type: 'mastercard', lastFour: '5555', expiry: '08/27', isDefault: false, holderName: 'Priya Sharma' },
]

const mockPricingPlans: PricingPlan[] = [
  {
    name: 'Starter',
    price: 49,
    color: 'blue',
    description: 'Perfect for getting started',
    features: ['10k messages/month', 'Basic API access', 'Community support', '2 integrations', '10 GB storage', '2 agents'],
    recommended: false,
  },
  {
    name: 'Growth',
    price: 149,
    color: 'purple',
    description: 'For growing teams',
    features: ['100k messages/month', 'Advanced API access', '24/7 support', '15+ integrations', '100 GB storage', '5 agents'],
    recommended: true,
  },
  {
    name: 'Enterprise',
    price: 499,
    color: 'amber',
    description: 'For large scale operations',
    features: ['Unlimited messages', 'Enterprise API', 'Dedicated support', 'Custom integrations', 'Unlimited storage', 'Unlimited agents'],
    recommended: false,
  },
]

// Utility Functions
const getPlanColor = (plan: string): string => {
  const colorMap: Record<string, string> = {
    starter: 'from-blue-500 to-blue-600',
    growth: 'from-purple-500 to-purple-600',
    enterprise: 'from-amber-500 to-amber-600',
  }
  return colorMap[plan] || colorMap.starter
}

const getBadgeColor = (plan: string): string => {
  const colorMap: Record<string, string> = {
    starter: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
    growth: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400',
    enterprise: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400',
  }
  return colorMap[plan] || colorMap.starter
}

const getStatusColor = (status: string): string => {
  switch (status) {
    case 'paid':
      return 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
    case 'pending':
      return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
    case 'failed':
      return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
    default:
      return 'bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-400'
  }
}

// Components
function UsageCard({
  title,
  used,
  limit,
  unit,
}: {
  title: string
  used: number
  limit: number
  unit: string
}) {
  const percentage = Math.round((used / limit) * 100)
  const isWarning = percentage > 80

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card className="h-full">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
              {title}
            </p>
            {isWarning && (
              <AlertCircle size={16} className="text-amber-500" />
            )}
          </div>
          <div className="mb-4">
            <p className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">
              {typeof used === 'number' && used % 1 !== 0
                ? used.toFixed(1)
                : used.toLocaleString()}{' '}
              <span className="text-sm font-normal text-neutral-500">
                / {limit.toLocaleString()} {unit}
              </span>
            </p>
          </div>
          <div className="w-full h-2 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
            <motion.div
              className={`h-full rounded-full ${
                percentage > 80 ? 'bg-amber-500' : 'bg-green-500'
              }`}
              initial={{ width: 0 }}
              animate={{ width: `${percentage}%` }}
              transition={{ duration: 0.6, ease: 'easeOut' }}
            />
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
            {percentage}% used
          </p>
        </CardContent>
      </Card>
    </motion.div>
  )
}

function PricingCard({
  plan,
  name,
  price,
  color,
  description,
  features,
  recommended,
  isCurrentPlan,
}: {
  plan: string
  name: string
  price: number
  color: string
  description: string
  features: string[]
  recommended: boolean
  isCurrentPlan: boolean
}) {
  const colorClasses: Record<string, string> = {
    blue: 'border-blue-500 dark:border-blue-500',
    purple: 'border-purple-500 dark:border-purple-500',
    amber: 'border-amber-500 dark:border-amber-500',
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="h-full"
    >
      <Card
        className={`h-full flex flex-col relative ${
          isCurrentPlan ? colorClasses[color] + ' border-2' : ''
        }`}
      >
        {recommended && !isCurrentPlan && (
          <div className="absolute -top-3 left-6 px-3 py-1 bg-gradient-to-r from-emerald-400 to-emerald-500 text-white text-xs font-semibold rounded-full">
            Recommended
          </div>
        )}
        {isCurrentPlan && (
          <div className="absolute top-4 right-4">
            <Badge className={getBadgeColor(plan)}>Current Plan</Badge>
          </div>
        )}

        <CardHeader>
          <CardTitle className="text-xl">{name}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>

        <CardContent className="flex-1">
          <div className="mb-6">
            <p className="text-3xl font-bold text-neutral-900 dark:text-neutral-50">
              ${price}{' '}
              <span className="text-sm font-normal text-neutral-500">
                /month
              </span>
            </p>
          </div>

          <div className="space-y-3">
            {features.map((feature: string) => (
              <div key={feature} className="flex items-start gap-3">
                <Check
                  size={16}
                  className="text-green-500 mt-0.5 flex-shrink-0"
                />
                <span className="text-sm text-neutral-700 dark:text-neutral-300">
                  {feature}
                </span>
              </div>
            ))}
          </div>
        </CardContent>

        <div className="px-6 py-4 border-t border-neutral-200 dark:border-neutral-800">
          {isCurrentPlan ? (
            <Button disabled className="w-full">
              Current Plan
            </Button>
          ) : price > mockCurrentSubscription.currentAmount ? (
            <Button className="w-full bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white">
              Upgrade
            </Button>
          ) : (
            <Button variant="outline" className="w-full">
              Downgrade
            </Button>
          )}
        </div>
      </Card>
    </motion.div>
  )
}

export default function BillingPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [subscriptionData, setSubscriptionData] = useState<Subscription>(mockCurrentSubscription as Subscription)
  const [usageData, setUsageData] = useState<UsageData>(mockUsageData as UsageData)
  const [invoices, setInvoices] = useState<Invoice[]>(mockInvoices as Invoice[])
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>(mockPaymentMethods as PaymentMethod[])
  const [usageHistory, setUsageHistory] = useState<UsageHistory[]>(mockUsageHistory as UsageHistory[])
  const { user } = useAuthStore()

  const fetchBillingData = useCallback(async () => {
    try {
      setError(null)
      setLoading(true)

      // Fetch subscription data
      try {
        const subResponse: any = await apiClient.get('/billing/api/v1/subscription')
        if (subResponse) {
          setSubscriptionData(subResponse as Subscription)
        }
      } catch {
        // Keep mock data on error
      }

      // Fetch usage data
      try {
        const usageResponse: any = await apiClient.get('/billing/api/v1/usage')
        if (usageResponse) {
          setUsageData(usageResponse as UsageData)
        }
      } catch {
        // Keep mock data on error
      }

      // Fetch invoice history
      try {
        const invoicesResponse: any = await apiClient.get('/billing/api/v1/invoices')
        if (invoicesResponse && Array.isArray(invoicesResponse)) {
          setInvoices(invoicesResponse as Invoice[])
        }
      } catch {
        // Keep mock data on error
      }

      // Fetch payment methods
      try {
        const paymentResponse: any = await apiClient.get('/billing/api/v1/payment-methods')
        if (paymentResponse && Array.isArray(paymentResponse)) {
          setPaymentMethods(paymentResponse as PaymentMethod[])
        }
      } catch {
        // Keep mock data on error
      }
    } catch (err) {
      console.error('Error fetching billing data:', err)
      setError('Failed to load some billing data. Showing cached results.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchBillingData()
  }, [fetchBillingData])

  const planName =
    subscriptionData.plan === 'starter'
      ? 'Starter'
      : subscriptionData.plan === 'growth'
        ? 'Growth'
        : 'Enterprise'

  const handleDownloadInvoice = (invoiceId: string) => {
    console.log('Downloading invoice:', invoiceId)
    // In production, this would trigger actual PDF download
  }

  return (
    <div className="min-h-screen bg-white dark:bg-neutral-950 p-6 md:p-8">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl md:text-4xl font-bold text-neutral-900 dark:text-white mb-2">
                Billing & Subscription
              </h1>
              <p className="text-neutral-600 dark:text-neutral-400">
                Manage your plan, invoices, and payment methods
              </p>
            </div>
            <motion.button
              onClick={fetchBillingData}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="p-2 rounded-lg bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
              disabled={loading}
              title="Refresh billing data"
            >
              <RefreshCw
                className={`w-5 h-5 text-neutral-700 dark:text-neutral-300 ${
                  loading ? 'animate-spin' : ''
                }`}
              />
            </motion.button>
          </div>
        </motion.div>

        {/* Error Banner */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-amber-800 dark:text-amber-200">
                {error}
              </p>
            </div>
          </motion.div>
        )}

        {/* Current Plan Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.05 }}
        >
          <Card
            className={`bg-gradient-to-br ${getPlanColor(subscriptionData.plan)} text-white relative overflow-hidden`}
          >
            <div className="absolute top-0 right-0 w-40 h-40 bg-white/10 rounded-full -mr-20 -mt-20" />
            <CardContent className="pt-8 pb-8 relative z-10">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div>
                  <p className="text-white/80 text-sm font-medium mb-2">
                    Current Plan
                  </p>
                  <h2 className="text-3xl font-bold">{planName}</h2>
                </div>
                <div>
                  <p className="text-white/80 text-sm font-medium mb-2">
                    Billing Cycle
                  </p>
                  <p className="text-2xl font-bold capitalize">
                    {subscriptionData.billingCycle}
                  </p>
                  <p className="text-white/70 text-sm mt-1">
                    ${subscriptionData.currentAmount}/month
                  </p>
                </div>
                <div>
                  <p className="text-white/80 text-sm font-medium mb-2">
                    Next Billing Date
                  </p>
                  <p className="text-2xl font-bold">
                    {new Date(
                      subscriptionData.nextBillingDate
                    ).toLocaleDateString()}
                  </p>
                  <Badge className="mt-2 bg-white/20 text-white border-white/30 hover:bg-white/30">
                    {subscriptionData.status.charAt(0).toUpperCase() +
                      subscriptionData.status.slice(1)}
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Usage Overview */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
        >
          <div>
            <h2 className="text-xl font-bold text-neutral-900 dark:text-white mb-4">
              Usage Overview
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {loading ? (
                <>
                  {[...Array(4)].map((_, i) => (
                    <Card key={i}>
                      <CardContent className="pt-6">
                        <div className="space-y-3">
                          <div className="h-4 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
                          <div className="h-8 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
                          <div className="h-2 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </>
              ) : (
                <>
                  <UsageCard
                    title="Messages Used"
                    used={usageData.messages.used}
                    limit={usageData.messages.limit}
                    unit={usageData.messages.unit}
                  />
                  <UsageCard
                    title="API Calls"
                    used={usageData.apiCalls.used}
                    limit={usageData.apiCalls.limit}
                    unit={usageData.apiCalls.unit}
                  />
                  <UsageCard
                    title="Storage"
                    used={usageData.storage.used}
                    limit={usageData.storage.limit}
                    unit={usageData.storage.unit}
                  />
                  <UsageCard
                    title="Active Agents"
                    used={usageData.agents.used}
                    limit={usageData.agents.limit}
                    unit={usageData.agents.unit}
                  />
                </>
              )}
            </div>
          </div>
        </motion.div>

        {/* Usage Chart */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.15 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp size={20} className="text-neutral-600 dark:text-neutral-400" />
                Usage Trend (Last 7 Days)
              </CardTitle>
              <CardDescription>
                Daily message and API call usage over the past week
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="h-64 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={usageHistory}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#e5e7eb"
                      className="dark:stroke-neutral-800"
                    />
                    <XAxis
                      dataKey="date"
                      stroke="#9ca3af"
                      className="dark:stroke-neutral-600"
                    />
                    <YAxis
                      stroke="#9ca3af"
                      className="dark:stroke-neutral-600"
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#fff',
                        border: '1px solid #e5e7eb',
                        borderRadius: '8px',
                      }}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="messages"
                      stroke="#8b5cf6"
                      strokeWidth={2}
                      dot={false}
                      name="Messages"
                    />
                    <Line
                      type="monotone"
                      dataKey="apiCalls"
                      stroke="#06b6d4"
                      strokeWidth={2}
                      dot={false}
                      name="API Calls"
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Pricing Plans Comparison */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
        >
          <div>
            <h2 className="text-xl font-bold text-neutral-900 dark:text-white mb-4">
              Pricing Plans
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {mockPricingPlans.map((plan) => (
                <PricingCard
                  key={plan.name}
                  plan={plan.name.toLowerCase()}
                  name={plan.name}
                  price={plan.price}
                  color={plan.color}
                  description={plan.description}
                  features={plan.features}
                  recommended={plan.recommended}
                  isCurrentPlan={
                    plan.name.toLowerCase() ===
                    subscriptionData.plan.toLowerCase()
                  }
                />
              ))}
            </div>
          </div>
        </motion.div>

        {/* Invoice History */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.25 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText size={20} className="text-neutral-600 dark:text-neutral-400" />
                Invoice History
              </CardTitle>
              <CardDescription>
                Your recent invoices and billing history
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-3">
                  {[...Array(3)].map((_, i) => (
                    <div
                      key={i}
                      className="h-16 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse"
                    />
                  ))}
                </div>
              ) : invoices.length === 0 ? (
                <div className="text-center py-8">
                  <FileText className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
                  <p className="text-neutral-600 dark:text-neutral-400">
                    No invoices yet
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-neutral-200 dark:border-neutral-800">
                        <th className="text-left px-4 py-3 text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase">
                          Invoice #
                        </th>
                        <th className="text-left px-4 py-3 text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase">
                          Date
                        </th>
                        <th className="text-left px-4 py-3 text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase">
                          Amount
                        </th>
                        <th className="text-left px-4 py-3 text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase">
                          Status
                        </th>
                        <th className="text-right px-4 py-3 text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase">
                          Action
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                      {invoices.map((invoice) => (
                        <tr
                          key={invoice.id}
                          className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition"
                        >
                          <td className="px-4 py-3 text-sm font-medium text-neutral-900 dark:text-white">
                            {invoice.id}
                          </td>
                          <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-400">
                            {new Date(invoice.date).toLocaleDateString()}
                          </td>
                          <td className="px-4 py-3 text-sm font-semibold text-neutral-900 dark:text-white">
                            ${invoice.amount.toFixed(2)}
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <Badge className={getStatusColor(invoice.status)}>
                              {invoice.status.charAt(0).toUpperCase() +
                                invoice.status.slice(1)}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <Button
                              variant="outline"
                              size="sm"
                              className="inline-flex items-center gap-2"
                              onClick={() =>
                                handleDownloadInvoice(invoice.id)
                              }
                            >
                              <Download size={14} /> Download
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Payment Methods */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.3 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CreditCard size={20} className="text-neutral-600 dark:text-neutral-400" />
                Payment Methods
              </CardTitle>
              <CardDescription>
                Manage your saved credit cards and payment information
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-3">
                  {[...Array(2)].map((_, i) => (
                    <div
                      key={i}
                      className="h-20 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse"
                    />
                  ))}
                </div>
              ) : paymentMethods.length === 0 ? (
                <div className="text-center py-8">
                  <CreditCard className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
                  <p className="text-neutral-600 dark:text-neutral-400 mb-4">
                    No payment methods saved
                  </p>
                  <Button variant="outline">Add Payment Method</Button>
                </div>
              ) : (
                <div className="space-y-4">
                  {paymentMethods.map((method) => (
                    <div
                      key={method.id}
                      className="flex items-center justify-between p-4 border border-neutral-200 dark:border-neutral-800 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition"
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-8 bg-gradient-to-br from-neutral-300 to-neutral-400 rounded flex items-center justify-center text-xs font-bold text-neutral-700">
                          {method.type.toUpperCase().substring(0, 2)}
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-neutral-900 dark:text-white">
                            {method.type.charAt(0).toUpperCase() +
                              method.type.slice(1)}{' '}
                            •••• {method.lastFour}
                          </p>
                          <p className="text-xs text-neutral-600 dark:text-neutral-400">
                            Expires {method.expiry} • {method.holderName}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {method.isDefault && (
                          <Badge className="bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400">
                            Default
                          </Badge>
                        )}
                        <Button variant="outline" size="sm">
                          Remove
                        </Button>
                      </div>
                    </div>
                  ))}
                  <Button
                    className="w-full mt-4"
                    variant="outline"
                  >
                    Add Payment Method
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  )
}
