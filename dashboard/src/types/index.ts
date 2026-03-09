export interface User {
  id: string
  email: string
  name: string
  avatar?: string
  role: 'admin' | 'agent' | 'viewer'
}

export interface Tenant {
  id: string
  name: string
  logo?: string
  plan: 'starter' | 'growth' | 'enterprise'
  status: 'active' | 'paused' | 'suspended'
  createdAt: Date
  updatedAt: Date
}

export interface AuthState {
  user: User | null
  tenant: Tenant | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

export interface Channel {
  id: string
  type: 'whatsapp' | 'email' | 'voice' | 'instagram' | 'facebook' | 'web' | 'sms' | 'telegram'
  name: string
  status: 'connected' | 'disconnected' | 'error'
  messageCount: number
  lastActive?: Date
  config?: Record<string, any>
}

export interface Contact {
  id: string
  name: string
  email?: string
  phone?: string
  avatar?: string
  channels: Channel['type'][]
}

export interface Message {
  id: string
  conversationId: string
  senderId: string
  senderType: 'customer' | 'ai' | 'agent'
  senderName: string
  senderAvatar?: string
  content: string
  channel: Channel['type']
  timestamp: Date
  isRead: boolean
  metadata?: Record<string, any>
}

export interface Conversation {
  id: string
  contactId: string
  contact: Contact
  channel: Channel['type']
  status: 'open' | 'closed' | 'waiting' | 'in_progress'
  lastMessage?: Message
  lastMessageAt: Date
  messageCount: number
  unreadCount: number
  aiHandling: boolean
  assignedAgent?: User
  leadScore: number
  tags: string[]
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
  history: Array<{
    id: string
    type: 'conversation_started' | 'agent_assigned' | 'ai_engaged' | 'ai_closed'
    timestamp: Date
    description: string
  }>
}

export interface Order {
  id: string
  contactId: string
  amount: number
  currency: string
  status: 'pending' | 'completed' | 'cancelled'
  createdAt: Date
  items: Array<{
    name: string
    quantity: number
    price: number
  }>
}

export interface CustomerProfile extends Contact {
  totalOrders: number
  totalSpent: number
  lastContact: Date
  leadScore: number
  conversationCount: number
  orders: Order[]
  tags: string[]
  notes: string
}

export interface DashboardStats {
  totalConversations: number
  revenueInfluenced: number
  avgResponseTime: number
  csatScore: number
  trend: {
    conversations: number
    revenue: number
    responseTime: number
    csat: number
  }
}

export interface FunnelData {
  stage: string
  value: number
  percentage: number
}

export interface ChannelStats {
  channel: Channel['type']
  count: number
  percentage: number
}

export interface APIResponse<T> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  businessName: string
  fullName: string
  email: string
  password: string
  confirmPassword: string
  agreedToTerms: boolean
}

export interface AIConfig {
  name: string
  personality: 'formal' | 'casual' | 'friendly'
  systemPrompt: string
  maxDiscount: number
  autoRespond: boolean
  businessContext: string
}

export interface TeamMember {
  id: string
  name: string
  email: string
  role: 'admin' | 'agent' | 'viewer'
  status: 'active' | 'invited' | 'inactive'
  joinedAt: Date
  lastActive?: Date
}

export interface BillingInfo {
  plan: 'starter' | 'growth' | 'enterprise'
  monthlyPrice: number
  currentUsage: {
    conversations: number
    limit: number
  }
  nextBillingDate: Date
  paymentMethod?: {
    type: string
    lastFour: string
  }
}
