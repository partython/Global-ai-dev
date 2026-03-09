// @ts-nocheck
'use client'

import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import {
  TrendingUp,
  MessageSquare,
  Clock,
  CheckCircle,
  Zap,
  DollarSign,
  Users,
  Phone,
  Mail,
  Globe,
  MessageCircle,
  ChevronUp,
  ChevronDown,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

// Mock data for fallbacks
const mockOverviewData = {
  totalConversations: 15420,
  messagesSent: 124850,
  avgResponseTime: 2.3,
  resolutionRate: 0.87,
  aiContainmentRate: 0.64,
  revenueInfluenced: 245000,
}

const mockConversationVolumeData = [
  { date: 'Mar 1', whatsapp: 280, email: 145, web: 220, sms: 95 },
  { date: 'Mar 2', whatsapp: 310, email: 160, web: 240, sms: 110 },
  { date: 'Mar 3', whatsapp: 295, email: 155, web: 235, sms: 105 },
  { date: 'Mar 4', whatsapp: 340, email: 180, web: 260, sms: 120 },
  { date: 'Mar 5', whatsapp: 325, email: 170, web: 250, sms: 115 },
  { date: 'Mar 6', whatsapp: 360, email: 190, web: 280, sms: 130 },
  { date: 'Mar 7', whatsapp: 375, email: 200, web: 290, sms: 140 },
  { date: 'Mar 8', whatsapp: 380, email: 205, web: 300, sms: 145 },
  { date: 'Mar 9', whatsapp: 390, email: 210, web: 310, sms: 150 },
  { date: 'Mar 10', whatsapp: 410, email: 220, web: 320, sms: 160 },
  { date: 'Mar 11', whatsapp: 425, email: 230, web: 335, sms: 170 },
  { date: 'Mar 12', whatsapp: 440, email: 240, web: 345, sms: 180 },
  { date: 'Mar 13', whatsapp: 455, email: 250, web: 360, sms: 190 },
  { date: 'Mar 14', whatsapp: 470, email: 260, web: 375, sms: 200 },
  { date: 'Mar 15', whatsapp: 485, email: 270, web: 385, sms: 210 },
]

const mockResponseTimeData = [
  { date: 'Mar 1', avg: 2.8, p95: 5.2, p99: 8.1 },
  { date: 'Mar 2', avg: 2.7, p95: 5.1, p99: 8.0 },
  { date: 'Mar 3', avg: 2.9, p95: 5.3, p99: 8.2 },
  { date: 'Mar 4', avg: 2.6, p95: 5.0, p99: 7.9 },
  { date: 'Mar 5', avg: 2.5, p95: 4.9, p99: 7.8 },
  { date: 'Mar 6', avg: 2.4, p95: 4.8, p99: 7.7 },
  { date: 'Mar 7', avg: 2.3, p95: 4.7, p99: 7.6 },
  { date: 'Mar 8', avg: 2.2, p95: 4.6, p99: 7.5 },
  { date: 'Mar 9', avg: 2.1, p95: 4.5, p99: 7.4 },
  { date: 'Mar 10', avg: 2.0, p95: 4.4, p99: 7.3 },
  { date: 'Mar 11', avg: 1.9, p95: 4.3, p99: 7.2 },
  { date: 'Mar 12', avg: 1.8, p95: 4.2, p99: 7.1 },
  { date: 'Mar 13', avg: 1.7, p95: 4.1, p99: 7.0 },
  { date: 'Mar 14', avg: 1.6, p95: 4.0, p99: 6.9 },
  { date: 'Mar 15', avg: 1.5, p95: 3.9, p99: 6.8 },
]

const mockAIPerformanceData = [
  { name: 'Resolved', value: 64, color: '#a3e635' },
  { name: 'Handed Off', value: 28, color: '#6b7280' },
  { name: 'Escalated', value: 8, color: '#ef4444' },
]

const mockChannelData = [
  {
    channel: 'WhatsApp',
    messages: 45230,
    avgResponse: 1.8,
    resolutionRate: 0.92,
    csat: 4.6,
    icon: MessageCircle,
  },
  {
    channel: 'Email',
    messages: 28450,
    avgResponse: 4.2,
    resolutionRate: 0.85,
    csat: 4.3,
    icon: Mail,
  },
  {
    channel: 'Web',
    messages: 35120,
    avgResponse: 2.1,
    resolutionRate: 0.88,
    csat: 4.5,
    icon: Globe,
  },
  {
    channel: 'SMS',
    messages: 16050,
    avgResponse: 3.5,
    resolutionRate: 0.80,
    csat: 4.2,
    icon: Phone,
  },
]

const mockAgentsData = [
  {
    name: 'Priya Sharma',
    conversations: 1245,
    avgResponse: 1.2,
    csat: 4.8,
    trend: 'up',
    change: 12,
  },
  {
    name: 'Amit Kumar',
    conversations: 1089,
    avgResponse: 1.5,
    csat: 4.7,
    trend: 'up',
    change: 8,
  },
  {
    name: 'Maya Patel',
    conversations: 987,
    avgResponse: 1.8,
    csat: 4.6,
    trend: 'up',
    change: 5,
  },
  {
    name: 'Rohan Singh',
    conversations: 876,
    avgResponse: 2.1,
    csat: 4.5,
    trend: 'down',
    change: -3,
  },
  {
    name: 'Divya Gupta',
    conversations: 756,
    avgResponse: 1.9,
    csat: 4.4,
    trend: 'up',
    change: 2,
  },
]

const mockSentimentData = [
  { date: 'Mar 1', positive: 58, neutral: 32, negative: 10 },
  { date: 'Mar 2', positive: 60, neutral: 30, negative: 10 },
  { date: 'Mar 3', positive: 62, neutral: 28, negative: 10 },
  { date: 'Mar 4', positive: 65, neutral: 26, negative: 9 },
  { date: 'Mar 5', positive: 67, neutral: 25, negative: 8 },
  { date: 'Mar 6', positive: 70, neutral: 22, negative: 8 },
  { date: 'Mar 7', positive: 72, neutral: 20, negative: 8 },
]

interface AnalyticsData {
  totalConversations: number
  messagesSent: number
  avgResponseTime: number
  resolutionRate: number
  aiContainmentRate: number
  revenueInfluenced: number
}

interface ConversationVolumeItem {
  date: string
  whatsapp: number
  email: number
  web: number
  sms: number
}

interface ResponseTimeItem {
  date: string
  avg: number
  p95: number
  p99: number
}

const StatCard = ({
  icon: Icon,
  label,
  value,
  unit,
  trend,
  trendValue,
  loading,
}: {
  icon: React.ElementType
  label: string
  value: string | number
  unit?: string
  trend?: 'up' | 'down'
  trendValue?: number
  loading?: boolean
}) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.3 }}
  >
    <Card className="border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-sm font-medium text-neutral-600 dark:text-neutral-400 mb-2">
              {label}
            </p>
            {loading ? (
              <div className="h-8 w-24 bg-neutral-200 dark:bg-neutral-800 rounded animate-pulse" />
            ) : (
              <p className="text-2xl font-bold text-neutral-900 dark:text-white">
                {value}
                {unit && <span className="text-lg ml-1">{unit}</span>}
              </p>
            )}
            {trend && trendValue !== undefined && (
              <div className="flex items-center gap-1 mt-2">
                {trend === 'up' ? (
                  <ChevronUp className="w-4 h-4 text-green-600" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-red-600" />
                )}
                <span
                  className={`text-sm font-medium ${
                    trend === 'up' ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {Math.abs(trendValue)}%
                </span>
              </div>
            )}
          </div>
          <div className="rounded-lg bg-neutral-100 dark:bg-neutral-900 p-3">
            <Icon className="w-6 h-6 text-neutral-700 dark:text-neutral-400" />
          </div>
        </div>
      </CardContent>
    </Card>
  </motion.div>
)

const LoadingSkeleton = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-32 bg-neutral-200 dark:bg-neutral-800 rounded-lg animate-pulse"
        />
      ))}
    </div>
    <div className="h-96 bg-neutral-200 dark:bg-neutral-800 rounded-lg animate-pulse" />
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="h-80 bg-neutral-200 dark:bg-neutral-800 rounded-lg animate-pulse" />
      <div className="h-80 bg-neutral-200 dark:bg-neutral-800 rounded-lg animate-pulse" />
    </div>
  </div>
)

const AnalyticsPage = () => {
  const [dateRange, setDateRange] = useState<'7d' | '30d' | '90d'>('30d')
  const [overviewData, setOverviewData] = useState<AnalyticsData | null>(null)
  const [conversationVolume, setConversationVolume] = useState<ConversationVolumeItem[]>([])
  const [responseTimeData, setResponseTimeData] = useState<ResponseTimeItem[]>([])
  const [aiPerformanceData, setAIPerformanceData] = useState<typeof mockAIPerformanceData>([])
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({
    key: 'messages',
    direction: 'desc',
  })
  const [loading, setLoading] = useState(true)
  const user = useAuthStore((state) => state.user)

  useEffect(() => {
    fetchAnalyticsData()
  }, [dateRange])

  const fetchAnalyticsData = async () => {
    setLoading(true)
    try {
      const [overview, volume, times, aiPerf]: any[] = await Promise.all([
        apiClient.get('/analytics/api/v1/overview', { params: { dateRange } }),
        apiClient.get('/analytics/api/v1/conversations/volume', { params: { dateRange } }),
        apiClient.get('/analytics/api/v1/response-times', { params: { dateRange } }),
        apiClient.get('/analytics/api/v1/ai-performance', { params: { dateRange } }),
      ])

      setOverviewData(overview.data || mockOverviewData)
      setConversationVolume(volume.data || mockConversationVolumeData)
      setResponseTimeData(times.data || mockResponseTimeData)
      setAIPerformanceData(aiPerf.data || mockAIPerformanceData)
    } catch (error) {
      console.error('Failed to fetch analytics:', error)
      setOverviewData(mockOverviewData)
      setConversationVolume(mockConversationVolumeData)
      setResponseTimeData(mockResponseTimeData)
      setAIPerformanceData(mockAIPerformanceData)
    } finally {
      setLoading(false)
    }
  }

  const sortedChannels = [...mockChannelData].sort((a, b) => {
    const key = sortConfig.key as keyof typeof a
    const aValue = a[key]
    const bValue = b[key]

    if (typeof aValue === 'number' && typeof bValue === 'number') {
      return sortConfig.direction === 'asc' ? aValue - bValue : bValue - aValue
    }

    return 0
  })

  const handleSort = (key: string) => {
    setSortConfig({
      key,
      direction:
        sortConfig.key === key && sortConfig.direction === 'asc' ? 'desc' : 'asc',
    })
  }

  if (loading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-neutral-900 dark:text-white mb-2">Analytics</h1>
          <p className="text-neutral-600 dark:text-neutral-400">
            Comprehensive insights into conversation metrics and performance
          </p>
        </div>
        <LoadingSkeleton />
      </div>
    )
  }

  const aiResolved = aiPerformanceData.find((d) => d.name === 'Resolved')?.value || 64
  const aiHandedOff = aiPerformanceData.find((d) => d.name === 'Handed Off')?.value || 28

  return (
    <div className="space-y-8 pb-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-neutral-900 dark:text-white mb-1">Analytics</h1>
            <p className="text-neutral-600 dark:text-neutral-400">
              Comprehensive insights into conversation metrics and performance
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={dateRange === '7d' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setDateRange('7d')}
              className={
                dateRange === '7d'
                  ? 'bg-neutral-900 dark:bg-white text-white dark:text-neutral-900'
                  : 'border-neutral-200 dark:border-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-900'
              }
            >
              7d
            </Button>
            <Button
              variant={dateRange === '30d' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setDateRange('30d')}
              className={
                dateRange === '30d'
                  ? 'bg-neutral-900 dark:bg-white text-white dark:text-neutral-900'
                  : 'border-neutral-200 dark:border-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-900'
              }
            >
              30d
            </Button>
            <Button
              variant={dateRange === '90d' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setDateRange('90d')}
              className={
                dateRange === '90d'
                  ? 'bg-neutral-900 dark:bg-white text-white dark:text-neutral-900'
                  : 'border-neutral-200 dark:border-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-900'
              }
            >
              90d
            </Button>
          </div>
        </div>
      </motion.div>

      {/* Key Metrics */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, staggerChildren: 0.05 }}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4"
      >
        <StatCard
          icon={MessageSquare}
          label="Total Conversations"
          value={overviewData?.totalConversations?.toLocaleString() || '0'}
          trend="up"
          trendValue={12}
          loading={loading}
        />
        <StatCard
          icon={MessageSquare}
          label="Messages Sent"
          value={(overviewData?.messagesSent || 0) / 1000}
          unit="K"
          trend="up"
          trendValue={8}
          loading={loading}
        />
        <StatCard
          icon={Clock}
          label="Avg Response Time"
          value={overviewData?.avgResponseTime?.toFixed(1) || '0'}
          unit="min"
          trend="down"
          trendValue={5}
          loading={loading}
        />
        <StatCard
          icon={CheckCircle}
          label="Resolution Rate"
          value={(overviewData?.resolutionRate || 0) * 100}
          unit="%"
          trend="up"
          trendValue={3}
          loading={loading}
        />
        <StatCard
          icon={Zap}
          label="AI Containment"
          value={(overviewData?.aiContainmentRate || 0) * 100}
          unit="%"
          trend="up"
          trendValue={6}
          loading={loading}
        />
        <StatCard
          icon={DollarSign}
          label="Revenue Influenced"
          value={overviewData?.revenueInfluenced ? `$${(overviewData.revenueInfluenced / 1000).toFixed(0)}K` : '$0'}
          trend="up"
          trendValue={15}
          loading={loading}
        />
      </motion.div>

      {/* Conversation Volume Chart */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <Card className="border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
          <CardHeader>
            <CardTitle className="text-neutral-900 dark:text-white">Conversation Volume</CardTitle>
            <CardDescription className="text-neutral-600 dark:text-neutral-400">
              Conversations by channel over the last {dateRange === '7d' ? '7' : dateRange === '30d' ? '30' : '90'} days
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={conversationVolume}>
                <defs>
                  <linearGradient id="colorWhatsApp" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorEmail" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorWeb" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#a78bfa" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorSMS" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#fbbf24" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#e5e7eb"
                  className="dark:stroke-neutral-800"
                />
                <XAxis
                  dataKey="date"
                  stroke="#9ca3af"
                  className="dark:stroke-neutral-600"
                  style={{ fontSize: '12px' }}
                />
                <YAxis
                  stroke="#9ca3af"
                  className="dark:stroke-neutral-600"
                  style={{ fontSize: '12px' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                  labelStyle={{ color: '#1f2937' }}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="whatsapp"
                  stackId="1"
                  stroke="#34d399"
                  fillOpacity={1}
                  fill="url(#colorWhatsApp)"
                  name="WhatsApp"
                />
                <Area
                  type="monotone"
                  dataKey="email"
                  stackId="1"
                  stroke="#60a5fa"
                  fillOpacity={1}
                  fill="url(#colorEmail)"
                  name="Email"
                />
                <Area
                  type="monotone"
                  dataKey="web"
                  stackId="1"
                  stroke="#a78bfa"
                  fillOpacity={1}
                  fill="url(#colorWeb)"
                  name="Web"
                />
                <Area
                  type="monotone"
                  dataKey="sms"
                  stackId="1"
                  stroke="#fbbf24"
                  fillOpacity={1}
                  fill="url(#colorSMS)"
                  name="SMS"
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </motion.div>

      {/* Response Time & AI Performance Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Response Time Trends */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <Card className="border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
            <CardHeader>
              <CardTitle className="text-neutral-900 dark:text-white">Response Time Trends</CardTitle>
              <CardDescription className="text-neutral-600 dark:text-neutral-400">
                Average, P95, and P99 response times
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={responseTimeData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#e5e7eb"
                    className="dark:stroke-neutral-800"
                  />
                  <XAxis
                    dataKey="date"
                    stroke="#9ca3af"
                    className="dark:stroke-neutral-600"
                    style={{ fontSize: '12px' }}
                  />
                  <YAxis
                    stroke="#9ca3af"
                    className="dark:stroke-neutral-600"
                    style={{ fontSize: '12px' }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                    }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="avg"
                    stroke="#6366f1"
                    strokeWidth={2}
                    dot={false}
                    name="Average"
                  />
                  <Line
                    type="monotone"
                    dataKey="p95"
                    stroke="#f97316"
                    strokeWidth={2}
                    dot={false}
                    name="P95"
                  />
                  <Line
                    type="monotone"
                    dataKey="p99"
                    stroke="#ef4444"
                    strokeWidth={2}
                    dot={false}
                    name="P99"
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>

        {/* AI Performance */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.25 }}
        >
          <Card className="border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
            <CardHeader>
              <CardTitle className="text-neutral-900 dark:text-white">AI Performance</CardTitle>
              <CardDescription className="text-neutral-600 dark:text-neutral-400">
                Conversation resolution breakdown
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-6">
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={aiPerformanceData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={90}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {aiPerformanceData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value) => [`${value}%`, 'Percentage']}
                      contentStyle={{
                        backgroundColor: '#ffffff',
                        border: '1px solid #e5e7eb',
                        borderRadius: '8px',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-lime-500" />
                      <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                        Resolved
                      </span>
                    </div>
                    <span className="text-sm font-bold text-neutral-900 dark:text-white">
                      {aiResolved}%
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-gray-500" />
                      <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                        Handed Off
                      </span>
                    </div>
                    <span className="text-sm font-bold text-neutral-900 dark:text-white">
                      {aiHandedOff}%
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-red-500" />
                      <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                        Escalated
                      </span>
                    </div>
                    <span className="text-sm font-bold text-neutral-900 dark:text-white">
                      {100 - aiResolved - aiHandedOff}%
                    </span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Channel Performance Table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.3 }}
      >
        <Card className="border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
          <CardHeader>
            <CardTitle className="text-neutral-900 dark:text-white">Channel Performance</CardTitle>
            <CardDescription className="text-neutral-600 dark:text-neutral-400">
              Performance metrics across communication channels
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-neutral-200 dark:border-neutral-800">
                    <th className="text-left py-3 px-4 font-semibold text-neutral-700 dark:text-neutral-300">
                      Channel
                    </th>
                    <th
                      className="text-left py-3 px-4 font-semibold text-neutral-700 dark:text-neutral-300 cursor-pointer hover:text-neutral-900 dark:hover:text-neutral-100"
                      onClick={() => handleSort('messages')}
                    >
                      Messages {sortConfig.key === 'messages' && (
                        <span className="ml-1">
                          {sortConfig.direction === 'asc' ? '↑' : '↓'}
                        </span>
                      )}
                    </th>
                    <th
                      className="text-left py-3 px-4 font-semibold text-neutral-700 dark:text-neutral-300 cursor-pointer hover:text-neutral-900 dark:hover:text-neutral-100"
                      onClick={() => handleSort('avgResponse')}
                    >
                      Avg Response {sortConfig.key === 'avgResponse' && (
                        <span className="ml-1">
                          {sortConfig.direction === 'asc' ? '↑' : '↓'}
                        </span>
                      )}
                    </th>
                    <th
                      className="text-left py-3 px-4 font-semibold text-neutral-700 dark:text-neutral-300 cursor-pointer hover:text-neutral-900 dark:hover:text-neutral-100"
                      onClick={() => handleSort('resolutionRate')}
                    >
                      Resolution {sortConfig.key === 'resolutionRate' && (
                        <span className="ml-1">
                          {sortConfig.direction === 'asc' ? '↑' : '↓'}
                        </span>
                      )}
                    </th>
                    <th
                      className="text-left py-3 px-4 font-semibold text-neutral-700 dark:text-neutral-300 cursor-pointer hover:text-neutral-900 dark:hover:text-neutral-100"
                      onClick={() => handleSort('csat')}
                    >
                      CSAT {sortConfig.key === 'csat' && (
                        <span className="ml-1">
                          {sortConfig.direction === 'asc' ? '↑' : '↓'}
                        </span>
                      )}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedChannels.map((channel, idx) => {
                    const Icon = channel.icon
                    return (
                      <tr
                        key={idx}
                        className="border-b border-neutral-100 dark:border-neutral-900 hover:bg-neutral-50 dark:hover:bg-neutral-900/50"
                      >
                        <td className="py-4 px-4">
                          <div className="flex items-center gap-2">
                            <Icon className="w-4 h-4 text-neutral-600 dark:text-neutral-500" />
                            <span className="font-medium text-neutral-900 dark:text-white">
                              {channel.channel}
                            </span>
                          </div>
                        </td>
                        <td className="py-4 px-4 text-neutral-700 dark:text-neutral-300">
                          {channel.messages.toLocaleString()}
                        </td>
                        <td className="py-4 px-4 text-neutral-700 dark:text-neutral-300">
                          {channel.avgResponse.toFixed(1)} min
                        </td>
                        <td className="py-4 px-4">
                          <Badge className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-400 border-0">
                            {(channel.resolutionRate * 100).toFixed(0)}%
                          </Badge>
                        </td>
                        <td className="py-4 px-4">
                          <div className="flex items-center gap-1">
                            <span className="font-semibold text-neutral-900 dark:text-white">
                              {channel.csat.toFixed(1)}
                            </span>
                            <span className="text-yellow-500">★</span>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Top Performing Agents */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.35 }}
      >
        <Card className="border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
          <CardHeader>
            <CardTitle className="text-neutral-900 dark:text-white">Top Performing Agents</CardTitle>
            <CardDescription className="text-neutral-600 dark:text-neutral-400">
              Agent leaderboard based on conversations and satisfaction
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {mockAgentsData.map((agent, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: idx * 0.05 }}
                  className="flex items-center justify-between p-4 rounded-lg bg-neutral-50 dark:bg-neutral-900/50 border border-neutral-200 dark:border-neutral-800/50 hover:bg-neutral-100 dark:hover:bg-neutral-800/50 transition-colors"
                >
                  <div className="flex items-center gap-4 flex-1">
                    <div className="flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 text-white font-bold text-sm">
                      {idx + 1}
                    </div>
                    <div className="flex-1">
                      <p className="font-semibold text-neutral-900 dark:text-white">
                        {agent.name}
                      </p>
                      <p className="text-sm text-neutral-600 dark:text-neutral-400">
                        {agent.conversations} conversations
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <p className="text-sm text-neutral-600 dark:text-neutral-400">Avg Response</p>
                      <p className="font-semibold text-neutral-900 dark:text-white">
                        {agent.avgResponse.toFixed(1)} min
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-neutral-600 dark:text-neutral-400">CSAT Rating</p>
                      <div className="flex items-center justify-end gap-1">
                        <span className="font-semibold text-neutral-900 dark:text-white">
                          {agent.csat.toFixed(1)}
                        </span>
                        <span className="text-yellow-500">★</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      {agent.trend === 'up' ? (
                        <ChevronUp className="w-5 h-5 text-green-600" />
                      ) : (
                        <ChevronDown className="w-5 h-5 text-red-600" />
                      )}
                      <span
                        className={`text-sm font-semibold ${
                          agent.trend === 'up' ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {Math.abs(agent.change)}%
                      </span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Sentiment Analysis */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.4 }}
      >
        <Card className="border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950">
          <CardHeader>
            <CardTitle className="text-neutral-900 dark:text-white">Sentiment Analysis</CardTitle>
            <CardDescription className="text-neutral-600 dark:text-neutral-400">
              Customer sentiment distribution over time
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={mockSentimentData}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#e5e7eb"
                  className="dark:stroke-neutral-800"
                />
                <XAxis
                  dataKey="date"
                  stroke="#9ca3af"
                  className="dark:stroke-neutral-600"
                  style={{ fontSize: '12px' }}
                />
                <YAxis
                  stroke="#9ca3af"
                  className="dark:stroke-neutral-600"
                  style={{ fontSize: '12px' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                  formatter={(value) => [`${value}%`, 'Percentage']}
                />
                <Legend />
                <Bar dataKey="positive" stackId="a" fill="#10b981" name="Positive" radius={[4, 4, 0, 0]} />
                <Bar dataKey="neutral" stackId="a" fill="#a1a5b4" name="Neutral" radius={[4, 4, 0, 0]} />
                <Bar dataKey="negative" stackId="a" fill="#ef4444" name="Negative" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}

export default AnalyticsPage
