// @ts-nocheck
'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Plus,
  Activity,
  Clock,
  TrendingUp,
  Play,
  Pause,
  MessageSquare,
  Calendar,
  Zap,
  CheckCircle,
  AlertCircle,
  ChevronDown,
  Copy,
  Edit,
  Trash2,
} from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

interface Workflow {
  id: string
  name: string
  description: string
  trigger: 'message_received' | 'schedule' | 'event' | 'manual'
  status: 'active' | 'inactive' | 'draft'
  executionCount: number
  lastRun: string | null
  successRate: number
  enabled: boolean
}

interface WorkflowStats {
  activeWorkflows: number
  totalExecutions24h: number
  successRate: number
  avgExecutionTime: number
}

interface Execution {
  id: string
  workflowName: string
  trigger: string
  startedAt: string
  duration: number
  status: 'success' | 'failed' | 'running'
  error?: string
}

interface ChartData {
  date: string
  executions: number
  successRate: number
}

const mockWorkflows: Workflow[] = [
  {
    id: '1',
    name: 'Welcome Message Flow',
    description: 'Automatically send welcome messages to new contacts',
    trigger: 'event',
    status: 'active',
    executionCount: 342,
    lastRun: '2 minutes ago',
    successRate: 98.5,
    enabled: true,
  },
  {
    id: '2',
    name: 'Lead Scoring Pipeline',
    description: 'Score leads based on engagement and interactions',
    trigger: 'message_received',
    status: 'active',
    executionCount: 1250,
    lastRun: '30 seconds ago',
    successRate: 99.2,
    enabled: true,
  },
  {
    id: '3',
    name: 'Auto-Escalation Rules',
    description: 'Route high-priority messages to support team',
    trigger: 'event',
    status: 'active',
    executionCount: 487,
    lastRun: '5 minutes ago',
    successRate: 97.8,
    enabled: true,
  },
  {
    id: '4',
    name: 'After-Hours Response',
    description: 'Send automated responses outside business hours',
    trigger: 'schedule',
    status: 'active',
    executionCount: 156,
    lastRun: '1 hour ago',
    successRate: 96.5,
    enabled: true,
  },
  {
    id: '5',
    name: 'Cart Recovery Sequence',
    description: 'Remind customers about abandoned carts',
    trigger: 'event',
    status: 'inactive',
    executionCount: 89,
    lastRun: '3 days ago',
    successRate: 94.2,
    enabled: false,
  },
]

const mockStats: WorkflowStats = {
  activeWorkflows: 4,
  totalExecutions24h: 2847,
  successRate: 98.2,
  avgExecutionTime: 1250,
}

const mockExecutions: Execution[] = [
  {
    id: '1',
    workflowName: 'Lead Scoring Pipeline',
    trigger: 'Message Received',
    startedAt: '2026-03-07 14:32:15',
    duration: 1250,
    status: 'success',
  },
  {
    id: '2',
    workflowName: 'Welcome Message Flow',
    trigger: 'Event',
    startedAt: '2026-03-07 14:28:42',
    duration: 892,
    status: 'success',
  },
  {
    id: '3',
    workflowName: 'Auto-Escalation Rules',
    trigger: 'Event',
    startedAt: '2026-03-07 14:25:10',
    duration: 356,
    status: 'success',
  },
  {
    id: '4',
    workflowName: 'Cart Recovery Sequence',
    trigger: 'Event',
    startedAt: '2026-03-07 14:22:05',
    duration: 2145,
    status: 'failed',
    error: 'Database connection timeout after 2000ms',
  },
  {
    id: '5',
    workflowName: 'Lead Scoring Pipeline',
    trigger: 'Message Received',
    startedAt: '2026-03-07 14:18:30',
    duration: 1100,
    status: 'success',
  },
  {
    id: '6',
    workflowName: 'After-Hours Response',
    trigger: 'Schedule',
    startedAt: '2026-03-07 14:15:00',
    duration: 745,
    status: 'running',
  },
]

const mockChartData: ChartData[] = [
  { date: 'Mar 01', executions: 2100, successRate: 97.8 },
  { date: 'Mar 02', executions: 2450, successRate: 98.1 },
  { date: 'Mar 03', executions: 2180, successRate: 97.5 },
  { date: 'Mar 04', executions: 2890, successRate: 98.5 },
  { date: 'Mar 05', executions: 2640, successRate: 98.2 },
  { date: 'Mar 06', executions: 3120, successRate: 99.1 },
  { date: 'Mar 07', executions: 2847, successRate: 98.2 },
]

const templates = [
  {
    id: 'template-1',
    name: 'Welcome Series',
    description: 'Greet new contacts with a multi-step welcome sequence',
    icon: MessageSquare,
  },
  {
    id: 'template-2',
    name: 'Lead Qualification',
    description: 'Automatically qualify leads based on predefined criteria',
    icon: Zap,
  },
  {
    id: 'template-3',
    name: 'Abandoned Cart',
    description: 'Recover lost sales with reminder sequences',
    icon: AlertCircle,
  },
  {
    id: 'template-4',
    name: 'Support Escalation',
    description: 'Route support tickets based on sentiment and priority',
    icon: Activity,
  },
  {
    id: 'template-5',
    name: 'Feedback Collection',
    description: 'Gather and analyze customer feedback automatically',
    icon: TrendingUp,
  },
]

const getTriggerIcon = (trigger: string) => {
  switch (trigger) {
    case 'message_received':
      return <MessageSquare className="w-4 h-4" />
    case 'schedule':
      return <Calendar className="w-4 h-4" />
    case 'event':
      return <Zap className="w-4 h-4" />
    case 'manual':
      return <Play className="w-4 h-4" />
    default:
      return <Activity className="w-4 h-4" />
  }
}

const getTriggerLabel = (trigger: string) => {
  switch (trigger) {
    case 'message_received':
      return 'Message Received'
    case 'schedule':
      return 'Schedule'
    case 'event':
      return 'Event'
    case 'manual':
      return 'Manual'
    default:
      return trigger
  }
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.2,
    },
  },
}

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: 'easeOut' },
  },
}

const statVariants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.4 },
  },
}

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>(mockWorkflows as Workflow[])
  const [stats, setStats] = useState<WorkflowStats>(mockStats as WorkflowStats)
  const [executions, setExecutions] = useState<Execution[]>(mockExecutions as Execution[])
  const [chartData, setChartData] = useState<ChartData[]>(mockChartData as ChartData[])
  const [loading, setLoading] = useState(true)
  const [expandedExecution, setExpandedExecution] = useState<string | null>(null)
  const [workflowToggle, setWorkflowToggle] = useState<Record<string, boolean>>({})
  const { isAuthenticated } = useAuthStore()

  useEffect(() => {
    const initializeWorkflowToggles = () => {
      const toggleStates: Record<string, boolean> = {}
      workflows.forEach((wf) => {
        toggleStates[wf.id] = wf.enabled
      })
      setWorkflowToggle(toggleStates)
    }

    initializeWorkflowToggles()
  }, [workflows])

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        if (isAuthenticated) {
          const [workflowsRes, statsRes, executionsRes]: any[] = await Promise.all([
            apiClient.get('/automation/api/v1/workflows'),
            apiClient.get('/automation/api/v1/workflows/stats'),
            apiClient.get('/automation/api/v1/executions'),
          ])

          if (workflowsRes.data) setWorkflows(workflowsRes.data)
          if (statsRes.data) setStats(statsRes.data)
          if (executionsRes.data) setExecutions(executionsRes.data)
        }
      } catch (error) {
        console.error('Failed to fetch workflows data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [isAuthenticated])

  const handleToggleWorkflow = (workflowId: string) => {
    setWorkflowToggle((prev) => ({
      ...prev,
      [workflowId]: !prev[workflowId],
    }))
    setWorkflows((prev) =>
      prev.map((wf) =>
        wf.id === workflowId ? { ...wf, enabled: !wf.enabled, status: !wf.enabled ? 'active' : 'inactive' } : wf
      )
    )
  }

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900 p-6">
      <motion.div initial="hidden" animate="visible" variants={containerVariants} className="space-y-6">
        {/* Header */}
        <motion.div variants={itemVariants} className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Workflows & Automation</h1>
            <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
              Create and manage automated workflows to streamline your operations
            </p>
          </div>
          <Button
            className="bg-blue-600 hover:bg-blue-700 text-white gap-2 shadow-lg hover:shadow-xl transition-shadow"
            size="lg"
          >
            <Plus className="w-5 h-5" />
            Create Workflow
          </Button>
        </motion.div>

        {/* Stats Grid */}
        <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            {
              title: 'Active Workflows',
              value: stats.activeWorkflows,
              icon: Activity,
              color: 'from-blue-500 to-blue-600',
            },
            {
              title: 'Total Executions (24h)',
              value: stats.totalExecutions24h.toLocaleString(),
              icon: Zap,
              color: 'from-emerald-500 to-emerald-600',
            },
            {
              title: 'Success Rate',
              value: `${stats.successRate.toFixed(1)}%`,
              icon: CheckCircle,
              color: 'from-green-500 to-green-600',
            },
            {
              title: 'Avg Execution Time',
              value: formatDuration(stats.avgExecutionTime),
              icon: Clock,
              color: 'from-orange-500 to-orange-600',
            },
          ].map((stat, idx) => {
            const Icon = stat.icon
            return (
              <motion.div key={idx} variants={statVariants}>
                <Card className="border-0 shadow-lg hover:shadow-xl transition-shadow dark:bg-slate-800/50 backdrop-blur-sm">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-slate-600 dark:text-slate-400">{stat.title}</p>
                        <p className="text-2xl font-bold text-slate-900 dark:text-white mt-2">{stat.value}</p>
                      </div>
                      <div className={`bg-gradient-to-br ${stat.color} p-3 rounded-lg`}>
                        <Icon className="w-6 h-6 text-white" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            )
          })}
        </motion.div>

        {/* Workflow List */}
        <motion.div variants={itemVariants}>
          <Card className="border-0 shadow-lg dark:bg-slate-800/50 backdrop-blur-sm">
            <CardHeader className="pb-4">
              <CardTitle className="text-xl text-slate-900 dark:text-white">Active Workflows</CardTitle>
              <CardDescription>Manage and monitor your automation workflows</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {workflows.map((workflow) => (
                  <motion.div
                    key={workflow.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="border border-slate-200 dark:border-slate-700 rounded-lg p-4 hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="font-semibold text-slate-900 dark:text-white">{workflow.name}</h3>
                          <Badge
                            variant={workflow.status === 'active' ? 'default' : 'secondary'}
                            className={
                              workflow.status === 'active'
                                ? 'bg-green-500/20 text-green-700 dark:text-green-400 border-0'
                                : 'bg-slate-500/20 text-slate-700 dark:text-slate-400 border-0'
                            }
                          >
                            {workflow.status.charAt(0).toUpperCase() + workflow.status.slice(1)}
                          </Badge>
                        </div>
                        <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">{workflow.description}</p>
                        <div className="flex items-center gap-4 text-sm">
                          <div className="flex items-center gap-1 text-slate-600 dark:text-slate-400">
                            {getTriggerIcon(workflow.trigger)}
                            <span>{getTriggerLabel(workflow.trigger)}</span>
                          </div>
                          <div className="flex items-center gap-1 text-slate-600 dark:text-slate-400">
                            <Activity className="w-4 h-4" />
                            <span>{workflow.executionCount} executions</span>
                          </div>
                          <div className="flex items-center gap-1 text-slate-600 dark:text-slate-400">
                            <CheckCircle className="w-4 h-4" />
                            <span>{workflow.successRate}% success</span>
                          </div>
                          {workflow.lastRun && (
                            <div className="flex items-center gap-1 text-slate-600 dark:text-slate-400">
                              <Clock className="w-4 h-4" />
                              <span>Last run: {workflow.lastRun}</span>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleWorkflow(workflow.id)}
                          className="hover:bg-slate-100 dark:hover:bg-slate-700"
                        >
                          {workflowToggle[workflow.id] ? (
                            <Pause className="w-4 h-4 text-orange-500" />
                          ) : (
                            <Play className="w-4 h-4 text-green-500" />
                          )}
                        </Button>
                        <Button variant="ghost" size="sm" className="hover:bg-slate-100 dark:hover:bg-slate-700">
                          <Edit className="w-4 h-4 text-blue-500" />
                        </Button>
                        <Button variant="ghost" size="sm" className="hover:bg-slate-100 dark:hover:bg-slate-700">
                          <Copy className="w-4 h-4 text-slate-500" />
                        </Button>
                        <Button variant="ghost" size="sm" className="hover:bg-slate-100 dark:hover:bg-slate-700">
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </Button>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Workflow Templates */}
        <motion.div variants={itemVariants}>
          <Card className="border-0 shadow-lg dark:bg-slate-800/50 backdrop-blur-sm">
            <CardHeader className="pb-4">
              <CardTitle className="text-xl text-slate-900 dark:text-white">Workflow Templates</CardTitle>
              <CardDescription>Start with pre-built automation templates</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                {templates.map((template) => {
                  const Icon = template.icon
                  return (
                    <motion.div
                      key={template.id}
                      whileHover={{ scale: 1.02 }}
                      className="border border-slate-200 dark:border-slate-700 rounded-lg p-4 hover:border-blue-300 dark:hover:border-blue-700 transition-colors cursor-pointer"
                    >
                      <div className="mb-3">
                        <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center mb-3">
                          <Icon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <h4 className="font-semibold text-slate-900 dark:text-white text-sm">{template.name}</h4>
                        <p className="text-xs text-slate-600 dark:text-slate-400 mt-2">{template.description}</p>
                      </div>
                      <Button variant="outline" size="sm" className="w-full text-xs border-blue-200 dark:border-blue-800">
                        Use Template
                      </Button>
                    </motion.div>
                  )
                })}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Performance Chart */}
        <motion.div variants={itemVariants}>
          <Card className="border-0 shadow-lg dark:bg-slate-800/50 backdrop-blur-sm">
            <CardHeader className="pb-4">
              <CardTitle className="text-xl text-slate-900 dark:text-white">Workflow Performance</CardTitle>
              <CardDescription>Execution volume and success rate over the last 7 days</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="w-full h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" className="dark:stroke-slate-700" />
                    <XAxis dataKey="date" stroke="#94a3b8" className="dark:stroke-slate-600" />
                    <YAxis stroke="#94a3b8" className="dark:stroke-slate-600" yAxisId="left" />
                    <YAxis
                      stroke="#94a3b8"
                      className="dark:stroke-slate-600"
                      yAxisId="right"
                      orientation="right"
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1e293b',
                        border: '1px solid #475569',
                        borderRadius: '8px',
                      }}
                      labelStyle={{ color: '#e2e8f0' }}
                      formatter={(value) => {
                        if (typeof value === 'number') {
                          return [value.toFixed(1), '']
                        }
                        return value
                      }}
                    />
                    <Legend wrapperStyle={{ color: '#e2e8f0' }} />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="executions"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={{ fill: '#3b82f6', r: 4 }}
                      activeDot={{ r: 6 }}
                      name="Daily Executions"
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="successRate"
                      stroke="#10b981"
                      strokeWidth={2}
                      dot={{ fill: '#10b981', r: 4 }}
                      activeDot={{ r: 6 }}
                      name="Success Rate (%)"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Execution Log */}
        <motion.div variants={itemVariants}>
          <Card className="border-0 shadow-lg dark:bg-slate-800/50 backdrop-blur-sm">
            <CardHeader className="pb-4">
              <CardTitle className="text-xl text-slate-900 dark:text-white">Recent Executions</CardTitle>
              <CardDescription>Latest workflow execution log</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700">
                      <th className="text-left py-3 px-4 font-semibold text-slate-700 dark:text-slate-300">
                        Workflow Name
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-700 dark:text-slate-300">Trigger</th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-700 dark:text-slate-300">
                        Started At
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-700 dark:text-slate-300">
                        Duration
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-700 dark:text-slate-300">Status</th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-700 dark:text-slate-300">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executions.map((execution) => (
                      <motion.tr
                        key={execution.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="border-b border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                      >
                        <td className="py-3 px-4 text-slate-900 dark:text-slate-100">{execution.workflowName}</td>
                        <td className="py-3 px-4 text-slate-600 dark:text-slate-400">{execution.trigger}</td>
                        <td className="py-3 px-4 text-slate-600 dark:text-slate-400">{execution.startedAt}</td>
                        <td className="py-3 px-4 text-slate-600 dark:text-slate-400">{formatDuration(execution.duration)}</td>
                        <td className="py-3 px-4">
                          <Badge
                            variant="outline"
                            className={
                              execution.status === 'success'
                                ? 'bg-green-500/10 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800'
                                : execution.status === 'failed'
                                  ? 'bg-red-500/10 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800'
                                  : 'bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800'
                            }
                          >
                            {execution.status === 'success' && <CheckCircle className="w-3 h-3 mr-1" />}
                            {execution.status === 'failed' && <AlertCircle className="w-3 h-3 mr-1" />}
                            {execution.status.charAt(0).toUpperCase() + execution.status.slice(1)}
                          </Badge>
                        </td>
                        <td className="py-3 px-4">
                          {execution.error && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setExpandedExecution(
                                  expandedExecution === execution.id ? null : execution.id
                                )
                              }
                              className="hover:bg-slate-100 dark:hover:bg-slate-700"
                            >
                              <ChevronDown
                                className={`w-4 h-4 transition-transform ${expandedExecution === execution.id ? 'rotate-180' : ''}`}
                              />
                            </Button>
                          )}
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Expanded Error Details */}
              {expandedExecution && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg"
                >
                  <div className="flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <h4 className="font-semibold text-red-900 dark:text-red-300 mb-1">Error Details</h4>
                      <p className="text-sm text-red-800 dark:text-red-400 font-mono">
                        {executions.find((e) => e.id === expandedExecution)?.error}
                      </p>
                    </div>
                  </div>
                </motion.div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Loading Skeleton */}
        {loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed inset-0 bg-black/20 backdrop-blur-sm flex items-center justify-center z-50"
          >
            <Card className="w-80 border-0 shadow-xl">
              <CardContent className="p-6">
                <div className="space-y-4">
                  <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded-lg animate-pulse" />
                  <div className="space-y-2">
                    <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded-lg animate-pulse" />
                    <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded-lg animate-pulse w-5/6" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </motion.div>
    </div>
  )
}
