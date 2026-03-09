// @ts-nocheck
'use client'

import React, { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  Send,
  MessageSquare,
  BarChart3,
  Plus,
  Search,
  Filter,
  ChevronDown,
  Calendar,
  Clock,
  TrendingUp,
  Mail,
  MessageCircle,
  Smartphone,
  Zap,
  X,
  CheckCircle,
  AlertCircle,
  Users,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'

// Mock data
const mockCampaigns = [
  {
    id: '1',
    name: 'Spring Sale Campaign',
    type: 'Email',
    status: 'active',
    sent: 15420,
    delivered: 15180,
    opened: 5562,
    clicked: 1668,
    createdDate: '2024-02-28',
    segmentSize: 20000,
    progress: 85,
  },
  {
    id: '2',
    name: 'Product Launch WhatsApp Blast',
    type: 'WhatsApp',
    status: 'active',
    sent: 8900,
    delivered: 8750,
    opened: 6300,
    clicked: 2540,
    createdDate: '2024-03-02',
    segmentSize: 10000,
    progress: 100,
  },
  {
    id: '3',
    name: 'Exclusive VIP Offer',
    type: 'SMS',
    status: 'completed',
    sent: 4320,
    delivered: 4298,
    opened: 3439,
    clicked: 1720,
    createdDate: '2024-02-20',
    segmentSize: 5000,
    progress: 100,
  },
  {
    id: '4',
    name: 'Reengagement Campaign',
    type: 'Email',
    status: 'draft',
    sent: 0,
    delivered: 0,
    opened: 0,
    clicked: 0,
    createdDate: '2024-03-06',
    segmentSize: 3500,
    progress: 25,
  },
  {
    id: '5',
    name: 'Flash Deal Notification',
    type: 'WhatsApp',
    status: 'paused',
    sent: 6200,
    delivered: 6050,
    opened: 3630,
    clicked: 910,
    createdDate: '2024-02-25',
    segmentSize: 8000,
    progress: 62,
  },
]

const mockStats = {
  activeCampaigns: 2,
  totalSent: 35020,
  avgOpenRate: 42.8,
  avgClickRate: 14.2,
}

const mockSegments = [
  { id: '1', name: 'All Contacts', count: 125400, lastUpdated: '2 hours ago' },
  { id: '2', name: 'High Value Customers', count: 8920, lastUpdated: '1 day ago' },
  { id: '3', name: 'New Leads', count: 3420, lastUpdated: '3 hours ago' },
  { id: '4', name: 'Inactive Users', count: 15680, lastUpdated: '5 days ago' },
  { id: '5', name: 'VIP Members', count: 1240, lastUpdated: '12 hours ago' },
]

const performanceData = [
  { campaign: 'Spring Sale', openRate: 36, clickRate: 10.8 },
  { campaign: 'Product Launch', openRate: 70.8, clickRate: 28.5 },
  { campaign: 'VIP Offer', openRate: 79.6, clickRate: 39.8 },
  { campaign: 'Flash Deal', openRate: 58.5, clickRate: 14.6 },
]

const abTestData = [
  {
    id: '1',
    campaignName: 'Spring Sale Campaign',
    variantA: { subject: 'Subject A - Limited Time', openRate: 34.2, clickRate: 9.5 },
    variantB: { subject: 'Subject B - Best Deals Now', openRate: 38.5, clickRate: 12.1 },
    winner: 'B',
  },
]

const StatCard = ({ icon: Icon, label, value, trend }) => (
  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
    <Card className="bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800">
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400">{label}</p>
            <p className="text-3xl font-bold text-neutral-900 dark:text-neutral-50 mt-2">{value}</p>
            {trend && (
              <p className="text-xs text-green-600 dark:text-green-400 mt-1 flex items-center gap-1">
                <TrendingUp size={12} /> {trend}
              </p>
            )}
          </div>
          <div className="p-3 bg-neutral-100 dark:bg-neutral-800 rounded-lg">
            <Icon size={24} className="text-neutral-600 dark:text-neutral-400" />
          </div>
        </div>
      </CardContent>
    </Card>
  </motion.div>
)

const CampaignTypeIcon = ({ type }) => {
  switch (type) {
    case 'Email':
      return <Mail size={16} className="text-blue-500" />
    case 'WhatsApp':
      return <MessageCircle size={16} className="text-green-500" />
    case 'SMS':
      return <Smartphone size={16} className="text-purple-500" />
    default:
      return <Send size={16} />
  }
}

const StatusBadge = ({ status }) => {
  const variants = {
    active: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
    completed: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
    draft: 'bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-400',
    paused: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-600',
  }
  return <Badge className={`${variants[status] || variants.draft}`}>{status.charAt(0).toUpperCase() + status.slice(1)}</Badge>
}

const CreateCampaignModal = ({ isOpen, onClose }) => {
  const [formData, setFormData] = useState({
    name: '',
    type: 'email',
    segment: 'all',
    message: '',
    scheduleDate: '',
  })

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onClose()
    setFormData({ name: '', type: 'email', segment: 'all', message: '', scheduleDate: '' })
  }

  if (!isOpen) return null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 dark:bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 w-full max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <div className="sticky top-0 bg-white dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-800 p-6 flex items-center justify-between">
          <h2 className="text-xl font-bold text-neutral-900 dark:text-neutral-50">Create New Campaign</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <div>
            <label className="block text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
              Campaign Name
            </label>
            <input
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              placeholder="e.g., Summer Sale Campaign"
              className="w-full px-4 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 focus:ring-2 focus:ring-blue-500 outline-none transition"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
                Campaign Type
              </label>
              <select
                name="type"
                value={formData.type}
                onChange={handleChange}
                className="w-full px-4 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 focus:ring-2 focus:ring-blue-500 outline-none transition"
              >
                <option value="email">Email</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="sms">SMS</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
                Target Segment
              </label>
              <select
                name="segment"
                value={formData.segment}
                onChange={handleChange}
                className="w-full px-4 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 focus:ring-2 focus:ring-blue-500 outline-none transition"
              >
                <option value="all">All Contacts</option>
                <option value="high-value">High Value Customers</option>
                <option value="new-leads">New Leads</option>
                <option value="inactive">Inactive Users</option>
                <option value="vip">VIP Members</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
              Message Template
            </label>
            <textarea
              name="message"
              value={formData.message}
              onChange={handleChange}
              placeholder="Enter your message or use template variables: {{firstName}}, {{lastName}}, {{couponCode}}"
              rows={6}
              className="w-full px-4 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 focus:ring-2 focus:ring-blue-500 outline-none transition resize-none"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
              Schedule Date (Optional)
            </label>
            <input
              type="datetime-local"
              name="scheduleDate"
              value={formData.scheduleDate}
              onChange={handleChange}
              className="w-full px-4 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 focus:ring-2 focus:ring-blue-500 outline-none transition"
            />
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="submit"
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition"
            >
              Create Campaign
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-900 dark:text-neutral-50 rounded-lg font-medium transition"
            >
              Cancel
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  )
}

export default function CampaignsPage() {
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [campaigns, setCampaigns] = useState(mockCampaigns)
  const [stats, setStats] = useState(mockStats)
  const [segments, setSegments] = useState(mockSegments)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        // Simulate API calls
        // const campaignsRes = await apiClient.get('/marketing/api/v1/campaigns')
        // const statsRes = await apiClient.get('/marketing/api/v1/campaigns/stats')
        // const segmentsRes = await apiClient.get('/marketing/api/v1/segments')
        // Use mock data as fallback
        setCampaigns(mockCampaigns)
        setStats(mockStats)
        setSegments(mockSegments)
      } catch (error) {
        console.error('Error fetching campaigns:', error)
        // Use mock data on error
        setCampaigns(mockCampaigns)
        setStats(mockStats)
        setSegments(mockSegments)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  const filteredCampaigns = campaigns.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.type.toLowerCase().includes(search.toLowerCase())
  )

  const openRate = (campaign) => ((campaign.opened / campaign.sent) * 100).toFixed(1)
  const clickRate = (campaign) => ((campaign.clicked / campaign.sent) * 100).toFixed(1)

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.1, delayChildren: 0.2 },
    },
  }

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">Campaigns</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">Manage and track all your marketing campaigns</p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition"
        >
          <Plus size={18} /> Create Campaign
        </button>
      </div>

      {/* Stats Grid */}
      <motion.div
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <StatCard
          icon={Zap}
          label="Active Campaigns"
          value={stats.activeCampaigns}
          trend="+1 this week"
        />
        <StatCard
          icon={Send}
          label="Total Sent"
          value={stats.totalSent.toLocaleString()}
          trend="+12% vs last week"
        />
        <StatCard
          icon={Mail}
          label="Avg Open Rate"
          value={`${stats.avgOpenRate}%`}
          trend="+2.5% improvement"
        />
        <StatCard
          icon={BarChart3}
          label="Avg Click Rate"
          value={`${stats.avgClickRate}%`}
          trend="+1.2% improvement"
        />
      </motion.div>

      {/* Search and Filter */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search campaigns by name or type..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-blue-500 outline-none transition"
          />
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition">
          <Filter size={16} /> Filter <ChevronDown size={14} />
        </button>
      </div>

      {/* Campaigns List */}
      <motion.div variants={itemVariants}>
        <Card className="bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800">
          <CardHeader>
            <CardTitle className="text-lg font-bold">All Campaigns</CardTitle>
            <CardDescription>{filteredCampaigns.length} campaigns</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {filteredCampaigns.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-neutral-500 dark:text-neutral-400">No campaigns found</p>
                </div>
              ) : (
                filteredCampaigns.map((campaign, idx) => (
                  <motion.div
                    key={campaign.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className="p-4 border border-neutral-100 dark:border-neutral-800 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition cursor-pointer"
                  >
                    <div className="space-y-3">
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3 flex-1">
                          <div className="p-2 bg-neutral-100 dark:bg-neutral-800 rounded-lg">
                            <CampaignTypeIcon type={campaign.type} />
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="font-semibold text-neutral-900 dark:text-neutral-50">
                                {campaign.name}
                              </h3>
                              <StatusBadge status={campaign.status} />
                            </div>
                            <p className="text-xs text-neutral-500 dark:text-neutral-400">
                              Created {campaign.createdDate} • Segment: {campaign.segmentSize.toLocaleString()}
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-1">
                            {campaign.type}
                          </p>
                        </div>
                      </div>

                      {/* Metrics Row */}
                      <div className="grid grid-cols-4 gap-4 text-sm">
                        <div className="bg-neutral-50 dark:bg-neutral-800/50 p-2 rounded">
                          <p className="text-xs text-neutral-500 dark:text-neutral-400">Sent</p>
                          <p className="font-semibold text-neutral-900 dark:text-neutral-50">
                            {campaign.sent.toLocaleString()}
                          </p>
                        </div>
                        <div className="bg-neutral-50 dark:bg-neutral-800/50 p-2 rounded">
                          <p className="text-xs text-neutral-500 dark:text-neutral-400">Delivered</p>
                          <p className="font-semibold text-neutral-900 dark:text-neutral-50">
                            {campaign.delivered.toLocaleString()}
                          </p>
                        </div>
                        <div className="bg-neutral-50 dark:bg-neutral-800/50 p-2 rounded">
                          <p className="text-xs text-neutral-500 dark:text-neutral-400">Open Rate</p>
                          <p className="font-semibold text-neutral-900 dark:text-neutral-50">
                            {campaign.sent > 0 ? openRate(campaign) : '0'}%
                          </p>
                        </div>
                        <div className="bg-neutral-50 dark:bg-neutral-800/50 p-2 rounded">
                          <p className="text-xs text-neutral-500 dark:text-neutral-400">Click Rate</p>
                          <p className="font-semibold text-neutral-900 dark:text-neutral-50">
                            {campaign.sent > 0 ? clickRate(campaign) : '0'}%
                          </p>
                        </div>
                      </div>

                      {/* Progress Bar */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-xs font-medium text-neutral-700 dark:text-neutral-300">Progress</p>
                          <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
                            {campaign.progress}%
                          </p>
                        </div>
                        <div className="w-full h-2 bg-neutral-200 dark:bg-neutral-800 rounded-full overflow-hidden">
                          <motion.div
                            className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full"
                            initial={{ width: 0 }}
                            animate={{ width: `${campaign.progress}%` }}
                            transition={{ duration: 0.8, ease: 'easeOut' }}
                          />
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Performance Chart */}
      <motion.div variants={itemVariants}>
        <Card className="bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800">
          <CardHeader>
            <CardTitle className="text-lg font-bold">Campaign Performance</CardTitle>
            <CardDescription>Open Rate vs Click Rate comparison</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={performanceData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="campaign" tick={{ fill: '#6b7280', fontSize: 12 }} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1f2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    color: '#f3f4f6',
                  }}
                  formatter={(value) => `${value.toFixed(1)}%`}
                />
                <Legend />
                <Bar dataKey="openRate" fill="#3b82f6" radius={[8, 8, 0, 0]} />
                <Bar dataKey="clickRate" fill="#10b981" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </motion.div>

      {/* Audience Segments */}
      <motion.div variants={itemVariants}>
        <Card className="bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800">
          <CardHeader>
            <CardTitle className="text-lg font-bold">Audience Segments</CardTitle>
            <CardDescription>Available segments for targeting</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {segments.map((segment, idx) => (
                <motion.div
                  key={segment.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.05 }}
                  className="flex items-center justify-between p-3 border border-neutral-100 dark:border-neutral-800 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-neutral-100 dark:bg-neutral-800 rounded-lg">
                      <Users size={16} className="text-neutral-600 dark:text-neutral-400" />
                    </div>
                    <div>
                      <p className="font-medium text-neutral-900 dark:text-neutral-50">{segment.name}</p>
                      <p className="text-xs text-neutral-500 dark:text-neutral-400">
                        {segment.count.toLocaleString()} contacts
                      </p>
                    </div>
                  </div>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">Updated {segment.lastUpdated}</p>
                </motion.div>
              ))}
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* A/B Test Results */}
      {abTestData.length > 0 && (
        <motion.div variants={itemVariants}>
          <Card className="bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800">
            <CardHeader>
              <CardTitle className="text-lg font-bold">A/B Test Results</CardTitle>
              <CardDescription>Active variant tests and performance</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {abTestData.map((test) => (
                  <motion.div
                    key={test.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="border border-neutral-100 dark:border-neutral-800 rounded-lg p-4 space-y-4"
                  >
                    <div>
                      <p className="font-semibold text-neutral-900 dark:text-neutral-50 mb-1">
                        {test.campaignName}
                      </p>
                      <p className="text-xs text-neutral-500 dark:text-neutral-400">Testing subject lines</p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Variant A */}
                      <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-lg p-3">
                        <p className="text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
                          Variant A
                        </p>
                        <p className="text-xs text-neutral-600 dark:text-neutral-400 mb-3 line-clamp-2">
                          {test.variantA.subject}
                        </p>
                        <div className="space-y-1 text-xs">
                          <div className="flex justify-between">
                            <span className="text-neutral-600 dark:text-neutral-400">Open Rate:</span>
                            <span className="font-semibold text-neutral-900 dark:text-neutral-50">
                              {test.variantA.openRate}%
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-neutral-600 dark:text-neutral-400">Click Rate:</span>
                            <span className="font-semibold text-neutral-900 dark:text-neutral-50">
                              {test.variantA.clickRate}%
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Variant B */}
                      <div
                        className={`rounded-lg p-3 ${
                          test.winner === 'B'
                            ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                            : 'bg-neutral-50 dark:bg-neutral-800/50'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-sm font-medium text-neutral-900 dark:text-neutral-50">
                            Variant B
                          </p>
                          {test.winner === 'B' && (
                            <CheckCircle size={16} className="text-green-600 dark:text-green-400" />
                          )}
                        </div>
                        <p className="text-xs text-neutral-600 dark:text-neutral-400 mb-3 line-clamp-2">
                          {test.variantB.subject}
                        </p>
                        <div className="space-y-1 text-xs">
                          <div className="flex justify-between">
                            <span className="text-neutral-600 dark:text-neutral-400">Open Rate:</span>
                            <span className="font-semibold text-neutral-900 dark:text-neutral-50">
                              {test.variantB.openRate}%
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-neutral-600 dark:text-neutral-400">Click Rate:</span>
                            <span className="font-semibold text-neutral-900 dark:text-neutral-50">
                              {test.variantB.clickRate}%
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="pt-2 border-t border-neutral-200 dark:border-neutral-700">
                      <p className="text-xs font-medium text-green-600 dark:text-green-400 flex items-center gap-1">
                        <TrendingUp size={12} /> Variant {test.winner} is performing {test.winner === 'B' ? 'better' : 'equally'}
                      </p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Create Campaign Modal */}
      <CreateCampaignModal isOpen={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  )
}
