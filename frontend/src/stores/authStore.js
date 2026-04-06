import { create } from 'zustand'

const TOKEN_KEY = 'icp-search-token'
const USER_KEY = 'icp-search-user'

function loadUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null') } catch { return null }
}

export const useAuthStore = create((set) => ({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: loadUser(),

  setToken: (token) => {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
    set({ token })
  },

  setUser: (user) => {
    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    } else {
      localStorage.removeItem(USER_KEY)
    }
    set({ user })
  },

  loginAsSubject: (subject) => {
    const token = (subject || 'dev-user').trim()
    localStorage.setItem(TOKEN_KEY, token)
    set({ token })
  },

  logout: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    set({ token: '', user: null })
  },
}))
