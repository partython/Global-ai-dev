import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { User, Tenant, AuthState } from '@/types'

interface AuthStore extends AuthState {
  setAuth: (data: { user: any; tenant: any; token: string }) => void
  logout: () => void
  setToken: (token: string) => void
  updateUser: (user: Partial<User>) => void
}

// ── SECURITY: Use sessionStorage instead of localStorage ──
// sessionStorage is cleared when the tab closes, reducing token theft window.
// localStorage persists indefinitely — if XSS occurs, attacker extracts token
// from localStorage even after user closes the browser.
//
// Future improvement: migrate to httpOnly cookie auth (server-side sessions)
// which eliminates client-side token storage entirely.

const safeStorage = createJSONStorage(() => {
  if (typeof window !== 'undefined') {
    return window.sessionStorage
  }
  // SSR fallback — in-memory storage
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
  }
})

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      tenant: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      setAuth: (data) =>
        set({
          user: data.user,
          tenant: data.tenant,
          token: data.token,
          isAuthenticated: true,
        }),
      logout: () => {
        // Clear sessionStorage completely on logout
        if (typeof window !== 'undefined') {
          window.sessionStorage.removeItem('priya-auth')
        }
        set({
          user: null,
          tenant: null,
          token: null,
          isAuthenticated: false,
        })
      },
      setToken: (token) => set({ token }),
      updateUser: (user) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...user } : null,
        })),
    }),
    {
      name: 'priya-auth',
      storage: safeStorage,
      partialize: (state) => ({
        user: state.user,
        tenant: state.tenant,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

// Alias for backward compatibility
export const useAuth = useAuthStore
