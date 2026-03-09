import { useAuth } from '@/stores/auth'
import { APIResponse, PaginatedResponse } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9000'

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean>
}

class APIClient {
  private baseURL: string

  constructor(baseURL: string) {
    this.baseURL = baseURL
  }

  private buildURL(endpoint: string, params?: Record<string, string | number | boolean>): string {
    const url = new URL(`${this.baseURL}${endpoint}`)
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, String(value))
      })
    }
    return url.toString()
  }

  private async request<T>(
    method: string,
    endpoint: string,
    options: RequestOptions = {}
  ): Promise<T> {
    const { params, ...fetchOptions } = options
    const url = this.buildURL(endpoint, params)

    const token = useAuth.getState().token
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(fetchOptions.headers as Record<string, string> || {}),
    }

    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const response = await fetch(url, {
      method,
      ...fetchOptions,
      headers,
      credentials: 'include',
    })

    if (response.status === 401) {
      useAuth.getState().logout()
      window.location.href = '/login'
      throw new Error('Unauthorized')
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.message || `${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>('GET', endpoint, options)
  }

  post<T>(endpoint: string, body?: any, options?: RequestOptions): Promise<T> {
    return this.request<T>('POST', endpoint, {
      ...options,
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  put<T>(endpoint: string, body?: any, options?: RequestOptions): Promise<T> {
    return this.request<T>('PUT', endpoint, {
      ...options,
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  patch<T>(endpoint: string, body?: any, options?: RequestOptions): Promise<T> {
    return this.request<T>('PATCH', endpoint, {
      ...options,
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>('DELETE', endpoint, options)
  }
}

export const api = new APIClient(API_URL)
export const apiClient = api

// Conversation endpoints
export const conversationAPI = {
  list: (page = 1, limit = 10, filters?: any) =>
    api.get(`/api/v1/conversations`, { params: { page, limit, ...filters } }),
  get: (id: string) => api.get(`/api/v1/conversations/${id}`),
  search: (query: string) => api.get(`/api/v1/conversations/search`, { params: { q: query } }),
  markAsRead: (id: string) => api.patch(`/api/v1/conversations/${id}/read`),
  assignAgent: (id: string, agentId: string) =>
    api.patch(`/api/v1/conversations/${id}/assign`, { agentId }),
  close: (id: string) => api.patch(`/api/v1/conversations/${id}/close`),
  addMessage: (id: string, content: string) =>
    api.post(`/api/v1/conversations/${id}/messages`, { content }),
}

// Customer endpoints
export const customerAPI = {
  list: (page = 1, limit = 10) =>
    api.get(`/api/v1/customers`, { params: { page, limit } }),
  get: (id: string) => api.get(`/api/v1/customers/${id}`),
  search: (query: string) => api.get(`/api/v1/customers/search`, { params: { q: query } }),
  updateProfile: (id: string, data: any) =>
    api.patch(`/api/v1/customers/${id}`, data),
  getOrders: (id: string) => api.get(`/api/v1/customers/${id}/orders`),
  getTags: (id: string) => api.get(`/api/v1/customers/${id}/tags`),
  addTag: (id: string, tag: string) =>
    api.post(`/api/v1/customers/${id}/tags`, { tag }),
}

// Channel endpoints
export const channelAPI = {
  list: () => api.get(`/api/v1/channels`),
  get: (id: string) => api.get(`/api/v1/channels/${id}`),
  connect: (type: string, config: any) =>
    api.post(`/api/v1/channels`, { type, config }),
  update: (id: string, config: any) =>
    api.patch(`/api/v1/channels/${id}`, config),
  disconnect: (id: string) => api.delete(`/api/v1/channels/${id}`),
  getStats: (id: string) => api.get(`/api/v1/channels/${id}/stats`),
}

// Dashboard endpoints
export const dashboardAPI = {
  getStats: () => api.get(`/api/v1/dashboard/stats`),
  getConversations: (limit = 5) =>
    api.get(`/api/v1/dashboard/conversations`, { params: { limit } }),
  getChannelDistribution: () =>
    api.get(`/api/v1/dashboard/channels/distribution`),
  getFunnelData: () =>
    api.get(`/api/v1/dashboard/funnel`),
  getRecentActivity: () =>
    api.get(`/api/v1/dashboard/activity`),
}

// Settings endpoints
export const settingsAPI = {
  getGeneral: () => api.get(`/api/v1/settings/general`),
  updateGeneral: (data: any) =>
    api.patch(`/api/v1/settings/general`, data),
  getAI: () => api.get(`/api/v1/settings/ai`),
  updateAI: (data: any) =>
    api.patch(`/api/v1/settings/ai`, data),
  getTeam: () => api.get(`/api/v1/settings/team`),
  inviteTeamMember: (email: string, role: string) =>
    api.post(`/api/v1/settings/team/invite`, { email, role }),
  removeTeamMember: (id: string) =>
    api.delete(`/api/v1/settings/team/${id}`),
  getBilling: () => api.get(`/api/v1/settings/billing`),
  getAPIKeys: () => api.get(`/api/v1/settings/api-keys`),
  createAPIKey: (name: string) =>
    api.post(`/api/v1/settings/api-keys`, { name }),
  revokeAPIKey: (id: string) =>
    api.delete(`/api/v1/settings/api-keys/${id}`),
}

export default api
