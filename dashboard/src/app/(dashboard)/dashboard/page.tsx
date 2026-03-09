// @ts-nocheck
'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  TrendingUp,
  TrendingDown,
  MessageSquare,
  Clock,
  Smile,
  Plus,
  RefreshCw,
  ChevronRight,
  Zap,
  Settings,
  Users,
  BookOpen,
  Wifi,
  WifiOff,
  Activity,
} from 'lucide-react';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/Avatar';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { useRealtimeMetrics } from '@/hooks/useRealtimeMetrics';

// ── Helper: Relative time formatting ──
function formatTimeAgo(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min${diffMins > 1 ? 's' : ''} ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
}

// Mock data fallbacks
const mockStats = {
  totalConversations: 1250,
  revenueInfluenced: 45000,
  avgResponseTime: 2.3,
  csatScore: 4.8,
  totalConversationsTrend: 12.5,
  revenueInfluencedTrend: 8.3,
  avgResponseTimeTrend: -5.2,
  csatScoreTrend: 2.1,
};

const mockConversations = [
  {
    id: '1',
    contactName: 'Sarah Anderson',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Sarah',
    lastMessage: 'Thanks for your help! This product is exactly what I needed.',
    channel: 'whatsapp',
    timeAgo: '5 mins',
    unread: true,
  },
  {
    id: '2',
    contactName: 'John Smith',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=John',
    lastMessage: 'Can you provide more details about the pricing plans?',
    channel: 'email',
    timeAgo: '2 hours',
    unread: false,
  },
  {
    id: '3',
    contactName: 'Emma Wilson',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Emma',
    lastMessage: "I'd like to schedule a demo for next week",
    channel: 'web',
    timeAgo: '4 hours',
    unread: true,
  },
  {
    id: '4',
    contactName: 'Michael Chen',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Michael',
    lastMessage: 'The implementation went smoothly',
    channel: 'whatsapp',
    timeAgo: '1 day',
    unread: false,
  },
  {
    id: '5',
    contactName: 'Jessica Martinez',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Jessica',
    lastMessage: 'Looking forward to the onboarding session',
    channel: 'email',
    timeAgo: '2 days',
    unread: false,
  },
];

const mockChannels = [
  { name: 'WhatsApp', value: 2400, color: '#25D366' },
  { name: 'Email', value: 1800, color: '#EA4335' },
  { name: 'Web', value: 1200, color: '#4285F4' },
  { name: 'SMS', value: 900, color: '#FFB81C' },
  { name: 'Instagram', value: 600, color: '#E4405F' },
];

const mockRevenue = [
  { month: 'Jan', revenue: 32000, target: 35000 },
  { month: 'Feb', revenue: 38000, target: 35000 },
  { month: 'Mar', revenue: 42000, target: 40000 },
  { month: 'Apr', revenue: 45000, target: 42000 },
  { month: 'May', revenue: 48000, target: 45000 },
  { month: 'Jun', revenue: 52000, target: 50000 },
];

const mockFunnel = [
  { stage: 'Leads', value: 8500, percentage: 100 },
  { stage: 'Qualified', value: 5100, percentage: 60 },
  { stage: 'Proposals', value: 3200, percentage: 38 },
  { stage: 'Customers', value: 1250, percentage: 15 },
];

interface DashboardStats {
  totalConversations: number;
  revenueInfluenced: number;
  avgResponseTime: number;
  csatScore: number;
  totalConversationsTrend: number;
  revenueInfluencedTrend: number;
  avgResponseTimeTrend: number;
  csatScoreTrend: number;
}

interface Conversation {
  id: string;
  contactName: string;
  avatar: string;
  lastMessage: string;
  channel: string;
  timeAgo: string;
  unread: boolean;
}

interface ChannelData {
  name: string;
  value: number;
  color: string;
}

interface RevenueData {
  month: string;
  revenue: number;
  target: number;
}

interface FunnelData {
  stage: string;
  value: number;
  percentage: number;
}

function StatCard({
  icon: Icon,
  label,
  value,
  trend,
  isPositive,
  loading,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  trend: number;
  isPositive: boolean;
  loading: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <Card className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary-500/10 to-accent-500/10 dark:from-primary-500/5 dark:to-accent-500/5" />
        <CardContent className="pt-6 relative z-10">
          {loading ? (
            <div className="space-y-3">
              <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
              <div className="h-4 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            </div>
          ) : (
            <>
              <div className="flex items-start justify-between mb-4">
                <div className="p-2 bg-primary-100 dark:bg-primary-900/30 rounded-lg">
                  <Icon className="w-5 h-5 text-primary-600 dark:text-primary-400" />
                </div>
                <div className="flex items-center gap-1">
                  {isPositive ? (
                    <TrendingUp className="w-4 h-4 text-green-500" />
                  ) : (
                    <TrendingDown className="w-4 h-4 text-red-500" />
                  )}
                  <span
                    className={`text-sm font-semibold ${
                      isPositive ? 'text-green-500' : 'text-red-500'
                    }`}
                  >
                    {Math.abs(trend).toFixed(1)}%
                  </span>
                </div>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                {label}
              </p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {typeof value === 'number' && label.includes('$')
                  ? `$${value.toLocaleString()}`
                  : typeof value === 'number'
                    ? value.toFixed(
                        label.includes('Response') || label.includes('CSAT')
                          ? 1
                          : 0,
                      )
                    : value}
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function SkeletonCard() {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="space-y-4">
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
          <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
          <div className="h-4 w-20 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        </div>
      </CardContent>
    </Card>
  );
}

function GettingStartedCard() {
  const checklistItems = [
    {
      icon: BookOpen,
      title: 'Upload Docs to Knowledge Base',
      completed: false,
    },
    {
      icon: Zap,
      title: 'Connect Your First Channel',
      completed: false,
    },
    {
      icon: Settings,
      title: 'Set Up Your AI Persona',
      completed: false,
    },
    {
      icon: Users,
      title: 'Invite Team Members',
      completed: false,
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <Card className="relative overflow-hidden border-primary-200 dark:border-primary-800 bg-gradient-to-br from-primary-50 to-accent-50 dark:from-primary-950/30 dark:to-accent-950/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            Getting Started
          </CardTitle>
          <CardDescription>
            Complete these steps to unlock the full power of your AI assistant
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3 mb-6">
            {checklistItems.map((item, idx) => (
              <div key={idx} className="flex items-center gap-3">
                <div className="w-5 h-5 rounded border-2 border-gray-300 dark:border-gray-600 flex items-center justify-center">
                  <div className="w-2 h-2 bg-gray-300 dark:bg-gray-600 rounded-sm" />
                </div>
                <span className="text-sm text-gray-700 dark:text-gray-300">
                  {item.title}
                </span>
              </div>
            ))}
          </div>
          <Button className="w-full bg-gradient-to-r from-primary-500 to-accent-500 hover:from-primary-600 hover:to-accent-600 text-white">
            Start Onboarding
            <ChevronRight className="w-4 h-4 ml-2" />
          </Button>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>(mockStats);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [channelData, setChannelData] = useState<ChannelData[]>(mockChannels);
  const [revenueData, setRevenueData] = useState<RevenueData[]>(mockRevenue);
  const [funnelData, setFunnelData] = useState<FunnelData[]>(mockFunnel);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [liveActiveConvs, setLiveActiveConvs] = useState<number | null>(null);
  const { user } = useAuthStore();

  // ── Real-time metrics via WebSocket ──
  const { metrics: realtimeMetrics, isConnected: metricsWsConnected } =
    useRealtimeMetrics({
      enabled: true,
      onMetricsUpdate: (m) => {
        setLiveActiveConvs(m.active_conversations);
      },
    });

  const isNewTenant =
    stats.totalConversations === 0 &&
    stats.revenueInfluenced === 0 &&
    stats.avgResponseTime === 0;

  // Channel color map for consistent styling
  const channelColorMap: Record<string, string> = {
    whatsapp: '#25D366',
    email: '#EA4335',
    web: '#4285F4',
    webchat: '#4285F4',
    sms: '#FFB81C',
    instagram: '#E4405F',
    facebook: '#1877F2',
    voice: '#9333EA',
    telegram: '#229ED9',
  };

  const fetchDashboardData = useCallback(async () => {
    try {
      setError(null);

      // ── 1. Dashboard metrics (maps to analytics service /api/v1/dashboard) ──
      try {
        const dashResponse: any = await apiClient.get('/analytics/api/v1/dashboard');
        if (dashResponse) {
          const d = dashResponse;
          setStats({
            totalConversations: d.total_conversations?.all_time ?? d.total_conversations ?? 0,
            revenueInfluenced: parseFloat(d.revenue_influenced ?? 0),
            avgResponseTime: d.average_response_time_ms
              ? d.average_response_time_ms / 1000
              : 0,
            csatScore: d.csat_score ?? 0,
            // Compute trends: comparing this_week to last week (rough approximation)
            totalConversationsTrend:
              d.total_conversations?.this_week && d.total_conversations?.this_month
                ? ((d.total_conversations.this_week / Math.max(d.total_conversations.this_month / 4, 1)) - 1) * 100
                : 0,
            revenueInfluencedTrend: 0,
            avgResponseTimeTrend: 0,
            csatScoreTrend: 0,
          });
        }
      } catch {
        // Keep mock stats on error
      }

      // ── 2. Recent conversations (from conversation service or analytics) ──
      try {
        const convsResponse: any = await apiClient.get(
          '/conversations/api/v1/list',
          { params: { limit: 5, status: 'open' } },
        );
        if (convsResponse?.data) {
          // Transform backend format to dashboard format
          const mapped = (convsResponse.data.items || convsResponse.data || []).map(
            (c: any) => ({
              id: c.id,
              contactName: c.contact?.name || c.contact_name || 'Unknown',
              avatar: c.contact?.avatar || `https://api.dicebear.com/7.x/avataaars/svg?seed=${c.contact?.name || c.id}`,
              lastMessage: c.last_message?.content || c.lastMessage || '',
              channel: c.channel || 'web',
              timeAgo: c.last_message_at
                ? formatTimeAgo(new Date(c.last_message_at))
                : c.lastMessageTime || '',
              unread: (c.unread_count || c.unreadCount || 0) > 0,
            })
          );
          if (mapped.length > 0) setConversations(mapped);
        }
      } catch {
        // Keep mock conversations on error
      }

      // ── 3. Channel distribution (from analytics /api/v1/channels/performance) ──
      try {
        const channelsResponse: any = await apiClient.get(
          '/analytics/api/v1/channels/performance',
        );
        if (channelsResponse?.channels) {
          const mapped = channelsResponse.channels
            .filter((ch: any) => ch.message_volume > 0)
            .map((ch: any) => ({
              name: ch.channel.charAt(0).toUpperCase() + ch.channel.slice(1),
              value: ch.message_volume,
              color: channelColorMap[ch.channel] || '#6B7280',
            }));
          if (mapped.length > 0) setChannelData(mapped);
        }
      } catch {
        // Keep mock channel data
      }

      // ── 4. Revenue trend (from analytics /api/v1/revenue) ──
      try {
        const revenueResponse: any = await apiClient.get('/analytics/api/v1/revenue');
        if (revenueResponse?.revenue_by_product) {
          // Transform product revenue into monthly trend if available
          // For now, use the totals to enrich existing chart
          const totalRev = parseFloat(revenueResponse.total_revenue || 0);
          if (totalRev > 0) {
            // Update stats with real revenue
            setStats((prev) => ({
              ...prev,
              revenueInfluenced: totalRev,
            }));
          }
        }
      } catch {
        // Keep mock revenue data
      }

      // ── 5. Funnel data (from analytics /api/v1/funnel) ──
      try {
        const funnelResponse: any = await apiClient.get('/analytics/api/v1/funnel');
        if (funnelResponse?.funnel_stages) {
          const totalLeads = funnelResponse.funnel_stages.reduce(
            (sum: number, s: any) => sum + s.count,
            0,
          );
          const mapped = funnelResponse.funnel_stages.map((s: any) => ({
            stage: s.stage.charAt(0).toUpperCase() + s.stage.slice(1),
            value: s.count,
            percentage:
              totalLeads > 0 ? Math.round((s.count / totalLeads) * 100) : 0,
          }));
          if (mapped.length > 0) setFunnelData(mapped);
        }
      } catch {
        // Keep mock funnel data
      }
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
      setError('Failed to load some data. Showing cached results.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();

    // Auto-refresh every 30 seconds (REST fallback when WS metrics aren't enough)
    const interval = setInterval(fetchDashboardData, 30000);

    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  return (
    <div className="min-h-screen bg-white dark:bg-gray-950 p-6 md:p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          className="mb-8"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-2">
                Dashboard
              </h1>
              <p className="text-gray-600 dark:text-gray-400">
                Welcome back, {user?.name || 'User'} 👋
              </p>
            </div>
            <div className="flex items-center gap-3">
              {/* Live metrics indicator */}
              <div
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-100 dark:bg-gray-800"
                title={metricsWsConnected ? 'Real-time metrics active' : 'Metrics polling (WebSocket disconnected)'}
              >
                {metricsWsConnected ? (
                  <Activity className="w-3.5 h-3.5 text-green-500 animate-pulse" />
                ) : (
                  <WifiOff className="w-3.5 h-3.5 text-gray-400" />
                )}
                <span className={`text-xs font-medium ${metricsWsConnected ? 'text-green-600 dark:text-green-400' : 'text-gray-500'}`}>
                  {metricsWsConnected ? 'Live' : 'Polling'}
                </span>
                {liveActiveConvs !== null && metricsWsConnected && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">
                    {liveActiveConvs} active
                  </span>
                )}
              </div>

              <motion.button
                onClick={fetchDashboardData}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="p-2 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                disabled={loading}
              >
                <RefreshCw
                  className={`w-5 h-5 text-gray-700 dark:text-gray-300 ${
                    loading ? 'animate-spin' : ''
                  }`}
                />
              </motion.button>
            </div>
          </div>
        </motion.div>

        {/* Error Banner */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 p-4 bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800 rounded-lg"
          >
            <p className="text-sm text-yellow-800 dark:text-yellow-200">
              {error}
            </p>
          </motion.div>
        )}

        {/* Getting Started (New Tenant) */}
        {isNewTenant && <GettingStartedCard />}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            icon={MessageSquare}
            label="Total Conversations"
            value={stats.totalConversations}
            trend={stats.totalConversationsTrend}
            isPositive={stats.totalConversationsTrend > 0}
            loading={loading}
          />
          <StatCard
            icon={TrendingUp}
            label="Revenue Influenced"
            value={`$${stats.revenueInfluenced}`}
            trend={stats.revenueInfluencedTrend}
            isPositive={stats.revenueInfluencedTrend > 0}
            loading={loading}
          />
          <StatCard
            icon={Clock}
            label="Avg Response Time"
            value={`${stats.avgResponseTime}s`}
            trend={stats.avgResponseTimeTrend}
            isPositive={stats.avgResponseTimeTrend < 0}
            loading={loading}
          />
          <StatCard
            icon={Smile}
            label="CSAT Score"
            value={stats.csatScore}
            trend={stats.csatScoreTrend}
            isPositive={stats.csatScoreTrend > 0}
            loading={loading}
          />
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
          {/* Recent Conversations */}
          <motion.div
            className="lg:col-span-2"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
          >
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Recent Conversations</CardTitle>
                    <CardDescription>Your latest customer chats</CardDescription>
                  </div>
                  <Button variant="ghost" size="sm">
                    View All
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="space-y-4">
                    {[...Array(3)].map((_, i) => (
                      <div key={i} className="h-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
                    ))}
                  </div>
                ) : conversations.length === 0 ? (
                  <div className="text-center py-8">
                    <MessageSquare className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                    <p className="text-gray-600 dark:text-gray-400">
                      No conversations yet
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {conversations.slice(0, 5).map((conv, idx) => (
                      <motion.div
                        key={conv.id}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.05 }}
                        className="flex items-start gap-4 p-3 hover:bg-gray-50 dark:hover:bg-gray-900/50 rounded-lg transition-colors cursor-pointer group"
                      >
                        <Avatar className="h-10 w-10 flex-shrink-0">
                          <AvatarImage src={conv.avatar} alt={conv.contactName} />
                          <AvatarFallback>
                            {conv.contactName
                              .split(' ')
                              .map((n) => n[0])
                              .join('')}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <p className="font-semibold text-gray-900 dark:text-white text-sm">
                              {conv.contactName}
                            </p>
                            <Badge
                              variant="secondary"
                              className="text-xs capitalize"
                            >
                              {conv.channel}
                            </Badge>
                            {conv.unread && (
                              <div className="w-2 h-2 rounded-full bg-primary-500" />
                            )}
                          </div>
                          <p className="text-sm text-gray-600 dark:text-gray-400 truncate">
                            {conv.lastMessage}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                            {conv.timeAgo}
                          </p>
                        </div>
                        <ChevronRight className="w-4 h-4 text-gray-400 dark:text-gray-600 group-hover:text-gray-600 dark:group-hover:text-gray-400 transition-colors flex-shrink-0" />
                      </motion.div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Channel Distribution */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Channel Distribution</CardTitle>
                <CardDescription>Messages by channel</CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="h-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
                ) : (
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie
                        data={channelData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={90}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {channelData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2937',
                          border: 'none',
                          borderRadius: '8px',
                          color: '#fff',
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                )}
                <div className="mt-4 space-y-2">
                  {channelData.map((channel, idx) => (
                    <div key={idx} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: channel.color }}
                        />
                        <span className="text-gray-600 dark:text-gray-400">
                          {channel.name}
                        </span>
                      </div>
                      <span className="font-semibold text-gray-900 dark:text-white">
                        {channel.value.toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          {/* Revenue Trend */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.3 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Revenue Trend</CardTitle>
                <CardDescription>Last 6 months vs target</CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="h-64 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
                ) : (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={revenueData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis dataKey="month" stroke="#9CA3AF" />
                      <YAxis stroke="#9CA3AF" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2937',
                          border: 'none',
                          borderRadius: '8px',
                          color: '#fff',
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="revenue"
                        stroke="#3b82f6"
                        strokeWidth={2}
                        name="Actual Revenue"
                        dot={{ fill: '#3b82f6', r: 4 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="target"
                        stroke="#10b981"
                        strokeWidth={2}
                        strokeDasharray="5 5"
                        name="Target"
                        dot={{ fill: '#10b981', r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Sales Funnel */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.4 }}
          >
            <Card>
              <CardHeader>
                <CardTitle>Sales Funnel</CardTitle>
                <CardDescription>Pipeline progression</CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="space-y-4">
                    {[...Array(4)].map((_, i) => (
                      <div key={i} className="h-12 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
                    ))}
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart
                      data={funnelData}
                      layout="vertical"
                      margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis type="number" stroke="#9CA3AF" />
                      <YAxis dataKey="stage" type="category" stroke="#9CA3AF" />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2937',
                          border: 'none',
                          borderRadius: '8px',
                          color: '#fff',
                        }}
                      />
                      <Bar
                        dataKey="value"
                        fill="#8b5cf6"
                        radius={[0, 8, 8, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                )}
                <div className="mt-4 space-y-2">
                  {funnelData.map((stage, idx) => (
                    <div key={idx} className="flex items-center justify-between text-sm">
                      <span className="text-gray-600 dark:text-gray-400">
                        {stage.stage}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-gray-900 dark:text-white">
                          {stage.value.toLocaleString()}
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-500">
                          ({stage.percentage}%)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* Quick Actions */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.5 }}
        >
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
              <CardDescription>Common next steps</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Button
                  variant="outline"
                  className="h-auto py-4 justify-center border-2 hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-primary-950/30"
                >
                  <div className="flex flex-col items-center gap-2">
                    <Plus className="w-5 h-5" />
                    <span>Connect Channel</span>
                  </div>
                </Button>
                <Button
                  variant="outline"
                  className="h-auto py-4 justify-center border-2 hover:border-accent-500 hover:bg-accent-50 dark:hover:bg-accent-950/30"
                >
                  <div className="flex flex-col items-center gap-2">
                    <Zap className="w-5 h-5" />
                    <span>Train AI</span>
                  </div>
                </Button>
                <Button
                  variant="outline"
                  className="h-auto py-4 justify-center border-2 hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950/30"
                >
                  <div className="flex flex-col items-center gap-2">
                    <ChevronRight className="w-5 h-5" />
                    <span>View Handoffs</span>
                  </div>
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
