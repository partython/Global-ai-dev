import { useRouter } from 'next/navigation'
import { useAuth } from '@/stores/auth'

// Use same-origin API routes (Next.js API at /api/auth/*)
const API_URL = ''

interface AuthResponse {
  token: string
  user: {
    id: string
    email: string
    name: string
    role: string
  }
  tenant: {
    id: string
    name: string
    plan: string
    status?: string
    createdAt?: any
    updatedAt?: any
  }
}

export async function loginUser(email: string, password: string): Promise<AuthResponse> {
  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.message || 'Login failed')
  }

  return response.json()
}

export async function registerUser(data: {
  businessName: string
  fullName: string
  email: string
  password: string
}): Promise<AuthResponse> {
  const response = await fetch(`${API_URL}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.message || 'Registration failed')
  }

  return response.json()
}

export async function loginWithGoogle(token: string): Promise<AuthResponse> {
  const response = await fetch(`${API_URL}/api/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })

  if (!response.ok) {
    throw new Error('Google login failed')
  }

  return response.json()
}

export async function logoutUser(): Promise<void> {
  // Client-side only logout — clear session storage
  // No server endpoint needed since we use stateless JWT
}

export async function refreshToken(currentToken: string): Promise<string> {
  // With stateless JWT, verify the current token is still valid
  const response = await fetch(`${API_URL}/api/auth/me`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${currentToken}`,
    },
  })

  if (!response.ok) {
    throw new Error('Token refresh failed')
  }

  // Return same token (JWT is self-contained)
  return currentToken
}

export function useAuthActions() {
  const router = useRouter()
  const setAuth = useAuth((state) => state.setAuth)
  const logout = useAuth((state) => state.logout)

  const handleLogin = async (email: string, password: string) => {
    const response = await loginUser(email, password)
    setAuth({
      user: response.user,
      tenant: response.tenant,
      token: response.token,
    })
    router.push('/dashboard')
  }

  const handleRegister = async (data: Parameters<typeof registerUser>[0]) => {
    const response = await registerUser(data)
    setAuth({
      user: response.user,
      tenant: response.tenant,
      token: response.token,
    })
    router.push('/dashboard?step=train')
  }

  const handleLogout = async () => {
    await logoutUser()
    logout()
    router.push('/')
  }

  return { handleLogin, handleRegister, handleLogout }
}
