import { create } from 'zustand'

export const useAuthStore = create((set) => ({
  authStatus: 'loading',
  isConfigured: false,
  token: '',
  user: null,

  setConfigured: (isConfigured) => set({ isConfigured }),
  setAuthStatus: (authStatus) => set({ authStatus }),
  setToken: (token) => set({ token: token || '' }),
  setUser: (user) => set({ user: user || null }),
  clearSession: () => set({ token: '', user: null, authStatus: 'unauthenticated' }),
}))
