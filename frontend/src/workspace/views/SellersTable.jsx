import React, { useEffect, useReducer } from 'react'
import { useUIStore } from '@/stores/uiStore'
import { useAuthStore } from '@/stores/authStore'
import { sellers as sellersApi } from '@/lib/api'
import { SkeletonRows } from '@/workspace/views/Skeleton'
import { formatDate } from '@/workspace/views/utils'

function reducer(state, action) {
  switch (action.type) {
    case 'loading': return { loading: true, data: [], error: null }
    case 'loaded':  return { loading: false, data: action.data, error: null }
    case 'error':   return { loading: false, data: [], error: action.error }
    default:        return state
  }
}

export default function SellersTable() {
  const token      = useAuthStore((s) => s.token)
  const openSeller = useUIStore((s) => s.openSeller)
  const [state, dispatch] = useReducer(reducer, { loading: false, data: [], error: null })

  useEffect(() => {
    if (!token) return
    dispatch({ type: 'loading' })
    sellersApi.list(token)
      .then((d) => dispatch({ type: 'loaded', data: Array.isArray(d) ? d : [] }))
      .catch((e) => dispatch({ type: 'error', error: e.message }))
  }, [token])

  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 bg-background z-10">
          <tr className="border-b border-border">
            <th className="text-left px-4 py-2.5 font-medium text-muted-foreground w-full">Name</th>
            <th className="text-left px-4 py-2.5 font-medium text-muted-foreground whitespace-nowrap">Created</th>
          </tr>
        </thead>
        <tbody>
          {state.loading && <SkeletonRows cols={2} rows={5} />}
          {state.error && (
            <tr><td colSpan={2} className="px-4 py-8 text-center text-sm text-destructive">{state.error}</td></tr>
          )}
          {!state.loading && !state.error && state.data.length === 0 && (
            <tr><td colSpan={2} className="px-4 py-12 text-center text-sm text-muted-foreground">No sellers yet</td></tr>
          )}
          {state.data.map((seller) => (
            <tr
              key={seller.id}
              onClick={() => openSeller(seller.id)}
              className="border-b border-border hover:bg-accent/50 cursor-pointer transition-colors"
            >
              <td className="px-4 py-2.5 font-medium">{seller.name}</td>
              <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">{formatDate(seller.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
