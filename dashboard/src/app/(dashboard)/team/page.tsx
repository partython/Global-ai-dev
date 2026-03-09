// @ts-nocheck
'use client'

import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  Users,
  UserCheck,
  Clock,
  SmilePlus,
  Send,
  MoreVertical,
  Trash2,
  Mail,
  Plus,
  UserX,
  RotateCcw,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/Avatar'
import { apiClient } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

// Mock data for team members
const MOCK_TEAM_MEMBERS = [
  {
    id: '1',
    name: 'Sarah Johnson',
    email: 'sarah@partython.ai',
    role: 'Admin',
    status: 'online',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Sarah',
    conversationsToday: 24,
    avgResponseTime: '2m 15s',
    csat: 4.8,
  },
  {
    id: '2',
    name: 'Marcus Chen',
    email: 'marcus@partython.ai',
    role: 'Agent',
    status: 'online',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Marcus',
    conversationsToday: 18,
    avgResponseTime: '3m 20s',
    csat: 4.6,
  },
  {
    id: '3',
    name: 'Priya Sharma',
    email: 'priya@partython.ai',
    role: 'Agent',
    status: 'online',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Priya',
    conversationsToday: 31,
    avgResponseTime: '1m 50s',
    csat: 4.9,
  },
  {
    id: '4',
    name: 'James Wilson',
    email: 'james@partython.ai',
    role: 'Agent',
    status: 'away',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=James',
    conversationsToday: 12,
    avgResponseTime: '4m 10s',
    csat: 4.3,
  },
  {
    id: '5',
    name: 'Emma Rodriguez',
    email: 'emma@partython.ai',
    role: 'Viewer',
    status: 'offline',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Emma',
    conversationsToday: 0,
    avgResponseTime: 'N/A',
    csat: 0,
  },
  {
    id: '6',
    name: 'David Thompson',
    email: 'david@partython.ai',
    role: 'Agent',
    status: 'online',
    avatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=David',
    conversationsToday: 22,
    avgResponseTime: '2m 45s',
    csat: 4.7,
  },
]

const MOCK_PENDING_INVITATIONS = [
  {
    id: '1',
    email: 'alice.kumar@email.com',
    role: 'Agent',
    invitedAt: '2026-03-05',
  },
  {
    id: '2',
    email: 'robert.lee@email.com',
    role: 'Agent',
    invitedAt: '2026-03-03',
  },
]

const MOCK_ACTIVE_SESSIONS = [
  {
    id: '1',
    agentName: 'Priya Sharma',
    conversationId: 'conv_1234567',
    customerName: 'John Doe',
    duration: '4m 23s',
    startTime: '14:32',
  },
  {
    id: '2',
    agentName: 'Sarah Johnson',
    conversationId: 'conv_7654321',
    customerName: 'Alice Smith',
    duration: '2m 10s',
    startTime: '14:45',
  },
  {
    id: '3',
    agentName: 'Marcus Chen',
    conversationId: 'conv_9876543',
    customerName: 'Bob Johnson',
    duration: '1m 55s',
    startTime: '14:48',
  },
]

// Type definitions
interface TeamMember {
  id: string
  name: string
  email: string
  role: 'Admin' | 'Agent' | 'Viewer'
  status: 'online' | 'offline' | 'away'
  avatar: string
  conversationsToday: number
  avgResponseTime: string
  csat: number
}

interface PendingInvitation {
  id: string
  email: string
  role: string
  invitedAt: string
}

interface ActiveSession {
  id: string
  agentName: string
  conversationId: string
  customerName: string
  duration: string
  startTime: string
}

interface TeamStats {
  totalMembers: number
  onlineNow: number
  avgHandleTime: string
  teamCsat: number
}

// Loading skeleton component
function TeamMemberSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-4 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
      <div className="h-4 bg-neutral-300 dark:bg-neutral-700 rounded w-5/6"></div>
      <div className="h-4 bg-neutral-300 dark:bg-neutral-700 rounded w-4/6"></div>
    </div>
  )
}

// Modal component for inviting members
function InviteMemberModal({ isOpen, onClose, onSubmit }: { isOpen: boolean; onClose: () => void; onSubmit: (data: { email: string; role: string }) => void }) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('Agent')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      onSubmit({ email, role })
      setEmail('')
      setRole('Agent')
      onClose()
    } finally {
      setLoading(false)
    }
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
        exit={{ scale: 0.95, opacity: 0 }}
        className="bg-white dark:bg-neutral-900 rounded-lg shadow-lg max-w-md w-full p-6 border border-neutral-200 dark:border-neutral-800"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Mail className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            <h2 className="text-xl font-bold text-neutral-900 dark:text-white">Invite Team Member</h2>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Email Address
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="member@example.com"
              required
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder-neutral-500 dark:placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Role
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
            >
              <option value="Admin">Admin</option>
              <option value="Agent">Agent</option>
              <option value="Viewer">Viewer</option>
            </select>
          </div>

          <div className="flex gap-3 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              className="flex-1 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={loading || !email}
              className="flex-1 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700 text-white"
            >
              {loading ? 'Sending...' : 'Send Invite'}
            </Button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  )
}

// Role badge component
function RoleBadge({ role }: { role: string }) {
  const colorMap: Record<string, string> = {
    Admin: 'bg-red-100 dark:bg-red-950 text-red-800 dark:text-red-200',
    Agent: 'bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-200',
    Viewer: 'bg-neutral-100 dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200',
  }
  return <Badge className={`${colorMap[role] || colorMap.Agent}`}>{role}</Badge>
}

// Status indicator component
function StatusIndicator({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    online: 'bg-green-500 dark:bg-green-600',
    offline: 'bg-neutral-400 dark:bg-neutral-600',
    away: 'bg-yellow-500 dark:bg-yellow-600',
  }
  return (
    <div className="flex items-center gap-2">
      <div className={`w-2.5 h-2.5 rounded-full ${colorMap[status] || colorMap.offline}`}></div>
      <span className="text-sm text-neutral-600 dark:text-neutral-400 capitalize">{status}</span>
    </div>
  )
}

// Main component
export default function TeamManagementPage() {
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>(MOCK_TEAM_MEMBERS)
  const [pendingInvitations, setPendingInvitations] = useState<PendingInvitation[]>(MOCK_PENDING_INVITATIONS)
  const [activeSessions, setActiveSessions] = useState<ActiveSession[]>(MOCK_ACTIVE_SESSIONS)
  const [stats, setStats] = useState<TeamStats>({
    totalMembers: 6,
    onlineNow: 4,
    avgHandleTime: '2m 47s',
    teamCsat: 4.72,
  })
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const { user } = useAuthStore()

  // Fetch team data
  useEffect(() => {
    const fetchTeamData = async () => {
      try {
        setLoading(true)
        // Attempt API call - fall back to mock data on failure
        try {
          const response = await apiClient.get('/api/v1/settings/team')
          if (response.data) {
            setTeamMembers(response.data.members || MOCK_TEAM_MEMBERS)
            setPendingInvitations(response.data.pendingInvitations || MOCK_PENDING_INVITATIONS)
            setStats(response.data.stats || stats)
          }
        } catch (apiError) {
          console.log('Using mock data for team members')
          // Continue with mock data
        }
      } finally {
        setLoading(false)
      }
    }

    fetchTeamData()
  }, [])

  // Handle invite submission
  const handleInviteSubmit = async (data: { email: string; role: string }) => {
    try {
      await apiClient.post('/api/v1/settings/team/invite', data)
      // Add to pending invitations list
      setPendingInvitations([
        ...pendingInvitations,
        {
          id: Math.random().toString(),
          email: data.email,
          role: data.role,
          invitedAt: new Date().toISOString().split('T')[0],
        },
      ])
    } catch (error) {
      console.error('Failed to send invite:', error)
    }
  }

  // Handle member removal
  const handleRemoveMember = async (memberId: string) => {
    try {
      setDeletingId(memberId)
      await apiClient.delete(`/api/v1/settings/team/${memberId}`)
      setTeamMembers(teamMembers.filter((m) => m.id !== memberId))
    } catch (error) {
      console.error('Failed to remove member:', error)
    } finally {
      setDeletingId(null)
    }
  }

  // Handle resend invitation
  const handleResendInvitation = async (invitationId: string) => {
    try {
      const invitation = pendingInvitations.find((i) => i.id === invitationId)
      if (invitation) {
        await apiClient.post('/api/v1/settings/team/invite', {
          email: invitation.email,
          role: invitation.role,
        })
      }
    } catch (error) {
      console.error('Failed to resend invitation:', error)
    }
  }

  // Handle cancel invitation
  const handleCancelInvitation = (invitationId: string) => {
    setPendingInvitations(pendingInvitations.filter((i) => i.id !== invitationId))
  }

  // Prepare chart data
  const chartData = teamMembers
    .filter((m) => m.role !== 'Viewer')
    .map((m) => ({
      name: m.name.split(' ')[0],
      conversations: m.conversationsToday,
      csat: m.csat * 20,
    }))

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-950 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between mb-8"
        >
          <div>
            <h1 className="text-3xl font-bold text-neutral-900 dark:text-white">Team Management</h1>
            <p className="text-neutral-600 dark:text-neutral-400 mt-1">
              Manage your team members and invite new collaborators
            </p>
          </div>
          <Button
            onClick={() => setIsModalOpen(true)}
            className="bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700 text-white gap-2"
          >
            <Plus className="w-4 h-4" />
            Invite Member
          </Button>
        </motion.div>

        {/* Team Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <Card className="border-neutral-200 dark:border-neutral-800 dark:bg-neutral-900">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
                    Total Members
                  </CardTitle>
                  <Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                </div>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <TeamMemberSkeleton />
                ) : (
                  <div className="text-3xl font-bold text-neutral-900 dark:text-white">{stats.totalMembers}</div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Card className="border-neutral-200 dark:border-neutral-800 dark:bg-neutral-900">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
                    Online Now
                  </CardTitle>
                  <UserCheck className="w-5 h-5 text-green-600 dark:text-green-400" />
                </div>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <TeamMemberSkeleton />
                ) : (
                  <div className="text-3xl font-bold text-neutral-900 dark:text-white">{stats.onlineNow}</div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Card className="border-neutral-200 dark:border-neutral-800 dark:bg-neutral-900">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
                    Avg Handle Time
                  </CardTitle>
                  <Clock className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                </div>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <TeamMemberSkeleton />
                ) : (
                  <div className="text-3xl font-bold text-neutral-900 dark:text-white">{stats.avgHandleTime}</div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            <Card className="border-neutral-200 dark:border-neutral-800 dark:bg-neutral-900">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
                    Team CSAT
                  </CardTitle>
                  <SmilePlus className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                </div>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <TeamMemberSkeleton />
                ) : (
                  <div className="text-3xl font-bold text-neutral-900 dark:text-white">{stats.teamCsat.toFixed(2)}</div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Team Members List */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="lg:col-span-2"
          >
            <Card className="border-neutral-200 dark:border-neutral-800 dark:bg-neutral-900">
              <CardHeader>
                <CardTitle>Team Members</CardTitle>
                <CardDescription>Manage your team members and their roles</CardDescription>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="space-y-4">
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="animate-pulse space-y-3 pb-4 border-b border-neutral-200 dark:border-neutral-800 last:border-b-0 last:pb-0">
                        <div className="h-4 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
                        <div className="h-4 bg-neutral-300 dark:bg-neutral-700 rounded w-5/6"></div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-4">
                    {teamMembers.map((member, index) => (
                      <motion.div
                        key={member.id}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.5 + index * 0.05 }}
                        className="flex items-start justify-between p-4 rounded-lg border border-neutral-200 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
                      >
                        <div className="flex items-start gap-4 flex-1">
                          <Avatar className="mt-0.5">
                            <AvatarImage src={member.avatar} alt={member.name} />
                            <AvatarFallback>{member.name.substring(0, 2)}</AvatarFallback>
                          </Avatar>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="font-semibold text-neutral-900 dark:text-white">{member.name}</h3>
                              <RoleBadge role={member.role} />
                            </div>
                            <p className="text-sm text-neutral-600 dark:text-neutral-400 truncate">{member.email}</p>
                            <div className="flex items-center gap-3 mt-2">
                              <StatusIndicator status={member.status} />
                              {member.conversationsToday > 0 && (
                                <span className="text-xs text-neutral-500 dark:text-neutral-500">
                                  {member.conversationsToday} conversations today
                                </span>
                              )}
                            </div>
                            {member.role !== 'Viewer' && (
                              <div className="flex items-center gap-4 mt-2 text-xs text-neutral-600 dark:text-neutral-400">
                                <span>Avg Response: {member.avgResponseTime}</span>
                                <span>CSAT: {member.csat > 0 ? member.csat.toFixed(1) : 'N/A'}</span>
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                          <select
                            defaultValue={member.role}
                            className="text-xs px-2 py-1 border border-neutral-300 dark:border-neutral-700 rounded bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                            onChange={() => {}}
                          >
                            <option value="Admin">Admin</option>
                            <option value="Agent">Agent</option>
                            <option value="Viewer">Viewer</option>
                          </select>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleRemoveMember(member.id)}
                            disabled={deletingId === member.id}
                            className="text-neutral-600 dark:text-neutral-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* Active Sessions */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
          >
            <Card className="border-neutral-200 dark:border-neutral-800 dark:bg-neutral-900 h-full">
              <CardHeader>
                <CardTitle className="text-lg">Active Sessions</CardTitle>
                <CardDescription>{activeSessions.length} ongoing conversations</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {activeSessions.map((session, index) => (
                    <motion.div
                      key={session.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.6 + index * 0.05 }}
                      className="p-3 rounded-lg bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700"
                    >
                      <p className="text-sm font-medium text-neutral-900 dark:text-white">{session.agentName}</p>
                      <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1">
                        with <span className="font-medium">{session.customerName}</span>
                      </p>
                      <div className="flex items-center justify-between mt-2 text-xs text-neutral-500 dark:text-neutral-500">
                        <span>{session.duration}</span>
                        <span className="text-neutral-400 dark:text-neutral-600">{session.startTime}</span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* Team Performance Chart */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7 }}
          className="mt-8"
        >
          <Card className="border-neutral-200 dark:border-neutral-800 dark:bg-neutral-900">
            <CardHeader>
              <CardTitle>Team Performance</CardTitle>
              <CardDescription>Conversations handled and CSAT scores by agent</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="animate-pulse h-64 bg-neutral-300 dark:bg-neutral-700 rounded"></div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="name" stroke="#666" />
                    <YAxis stroke="#666" />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1f2937',
                        border: '1px solid #374151',
                        borderRadius: '8px',
                        color: '#f3f4f6',
                      }}
                    />
                    <Legend />
                    <Bar dataKey="conversations" fill="#3b82f6" name="Conversations" radius={[8, 8, 0, 0]} />
                    <Bar dataKey="csat" fill="#10b981" name="CSAT (%)" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Pending Invitations */}
        {pendingInvitations.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8 }}
            className="mt-8"
          >
            <Card className="border-neutral-200 dark:border-neutral-800 dark:bg-neutral-900">
              <CardHeader>
                <CardTitle>Pending Invitations</CardTitle>
                <CardDescription>{pendingInvitations.length} pending invites</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {pendingInvitations.map((invitation, index) => (
                    <motion.div
                      key={invitation.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.8 + index * 0.05 }}
                      className="flex items-center justify-between p-4 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/50"
                    >
                      <div className="flex-1">
                        <p className="font-medium text-neutral-900 dark:text-white">{invitation.email}</p>
                        <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
                          Invited as <span className="font-medium">{invitation.role}</span> on{' '}
                          {new Date(invitation.invitedAt).toLocaleDateString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleResendInvitation(invitation.id)}
                          className="border-neutral-300 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 gap-1"
                        >
                          <RotateCcw className="w-3 h-3" />
                          Resend
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleCancelInvitation(invitation.id)}
                          className="text-neutral-600 dark:text-neutral-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </div>

      {/* Invite Member Modal */}
      <InviteMemberModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onSubmit={handleInviteSubmit} />
    </div>
  )
}
