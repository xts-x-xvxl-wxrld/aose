import React, { useEffect, useReducer } from 'react'
import { Target, Building2, Users, AlertCircle } from 'lucide-react'
import { useUIStore } from '@/stores/uiStore'
import { useAuthStore } from '@/stores/authStore'
import { sellers as sellersApi } from '@/lib/api'
import { formatDate } from '@/workspace/views/utils'
import { cn } from '@/lib/utils'

const CARDS = [
  { key: 'icps',     label: 'ICPs',     icon: Target,    type: 'icps' },
  { key: 'accounts', label: 'Accounts', icon: Building2, type: 'accounts' },
  { key: 'contacts', label: 'Contacts', icon: Users,     type: 'contacts' },
]

function reducer(state, action) {
  switch (action.type) {
    case 'loading':      return { ...state, loading: true, error: null }
    case 'loaded':       return { loading: false, summary: action.summary, seller: action.seller, error: null }
    case 'error':        return { ...state, loading: false, error: action.error }
    default:             return state
  }
}

export default function SellerOverview({ sellerId }) {
  const token          = useAuthStore((s) => s.token)
  const openObjectType = useUIStore((s) => s.openObjectType)
  const [state, dispatch] = useReducer(reducer, { loading: false, summary: null, seller: null, error: null })

  useEffect(() => {
    if (!token || !sellerId) return
    dispatch({ type: 'loading' })
    Promise.all([
      sellersApi.summary(token, sellerId),
      sellersApi.get(token, sellerId),
    ])
      .then(([summary, seller]) => dispatch({ type: 'loaded', summary, seller }))
      .catch((e) => dispatch({ type: 'error', error: e.message }))
  }, [token, sellerId])

  if (state.loading) return <OverviewSkeleton />
  if (state.error)   return <div className="p-6 text-sm text-destructive">{state.error}</div>
  if (!state.summary) return null

  const { summary, seller } = state

  return (
    <div className="h-full overflow-auto p-6">
      {/* Seller name */}
      <h2 className="text-xl font-semibold mb-1">{seller?.name}</h2>
      <p className="text-sm text-muted-foreground mb-6">Seller overview</p>

      {/* Instruction alert */}
      {summary.pending_instruction_alerts > 0 && (
        <div className="flex items-center gap-2 mb-6 p-3 rounded-lg border border-yellow-200 bg-yellow-50 dark:border-yellow-900/40 dark:bg-yellow-950/20 text-sm">
          <AlertCircle size={15} className="text-yellow-600 dark:text-yellow-400 flex-shrink-0" />
          <span className="text-yellow-800 dark:text-yellow-200">
            {summary.pending_instruction_alerts} agent instruction{summary.pending_instruction_alerts > 1 ? 's' : ''} pending review
          </span>
        </div>
      )}

      {/* Object type cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {CARDS.map((card) => {
          const data = summary[card.key] || {}
          const Icon = card.icon
          return (
            <button
              key={card.key}
              onClick={() => openObjectType(card.type)}
              className={cn(
                'flex flex-col gap-3 p-4 rounded-xl border border-border',
                'hover:bg-accent/50 hover:border-accent transition-colors text-left',
                'group',
              )}
            >
              <div className="flex items-center justify-between">
                <Icon size={16} className="text-muted-foreground group-hover:text-foreground transition-colors" />
                <span className="text-xs text-muted-foreground">{card.label}</span>
              </div>
              <div>
                <p className="text-2xl font-bold tabular-nums">{data.count ?? 0}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {data.last_added ? `Last added ${formatDate(data.last_added)}` : 'None added yet'}
                </p>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function OverviewSkeleton() {
  return (
    <div className="p-6 animate-pulse">
      <div className="h-7 w-48 bg-muted rounded mb-2" />
      <div className="h-4 w-32 bg-muted rounded mb-8" />
      <div className="grid grid-cols-3 gap-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-28 bg-muted rounded-xl" />
        ))}
      </div>
    </div>
  )
}
