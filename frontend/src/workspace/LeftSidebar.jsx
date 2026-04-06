import React, { useEffect, useReducer, useCallback, useState } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import * as Tooltip from '@radix-ui/react-tooltip'
import {
  MessageSquare,
  Search,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronRight,
  Building2,
  Target,
  Users,
  Briefcase,
  Plus,
  Loader2,
  ShieldCheck,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/uiStore'
import { useAuthStore } from '@/stores/authStore'
import { sellers as sellersApi } from '@/lib/api'
import AddSellerDialog from '@/workspace/actions/dialogs/AddSellerDialog'

// ── Category config ───────────────────────────────────────────────────────────

const CATEGORIES = [
  { key: 'icps',     label: 'ICPs',      icon: Target  },
  { key: 'accounts', label: 'Accounts',  icon: Building2 },
  { key: 'contacts', label: 'Contacts',  icon: Users },
]

// ── Sellers state (local to sidebar) ─────────────────────────────────────────

function sellersReducer(state, action) {
  switch (action.type) {
    case 'loading': return { ...state, loading: true, error: null }
    case 'loaded':  return { ...state, loading: false, data: action.data }
    case 'error':   return { ...state, loading: false, error: action.error }
    default:        return state
  }
}

// ── Main component ────────────────────────────────────────────────────────────

export default function LeftSidebar() {
  const leftOpen         = useUIStore((s) => s.leftSidebarOpen)
  const toggleSidebar    = useUIStore((s) => s.toggleLeftSidebar)
  const mainMode         = useUIStore((s) => s.mainMode)
  const activeSellerId   = useUIStore((s) => s.activeSellerId)
  const activeObjectType = useUIStore((s) => s.activeObjectType)
  const openChat         = useUIStore((s) => s.openChat)
  const openSeller       = useUIStore((s) => s.openSeller)
  const openObjectType   = useUIStore((s) => s.openObjectType)
  const token            = useAuthStore((s) => s.token)
  const currentUser      = useAuthStore((s) => s.user)

  const [addSellerOpen, setAddSellerOpen] = useState(false)

  const [sellers, dispatch] = useReducer(sellersReducer, {
    loading: false, data: [], error: null,
  })

  // Track which seller sub-trees are open in the sidebar (independent of active state)
  const [expandedIds, setExpandedIds] = React.useState(new Set())

  // Load sellers on mount
  useEffect(() => {
    if (!token) return
    dispatch({ type: 'loading' })
    sellersApi.list(token)
      .then((data) => dispatch({ type: 'loaded', data: Array.isArray(data) ? data : [] }))
      .catch((err) => dispatch({ type: 'error', error: err.message }))
  }, [token])

  // Auto-expand active seller in the tree
  useEffect(() => {
    if (activeSellerId) {
      setExpandedIds((prev) => new Set([...prev, activeSellerId]))
    }
  }, [activeSellerId])

  const toggleExpanded = useCallback((id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const handleSellerClick = useCallback((seller) => {
    openSeller(seller.id)
    setExpandedIds((prev) => new Set([...prev, seller.id]))
  }, [openSeller])

  const handleCategoryClick = useCallback((sellerId, categoryKey) => {
    // Ensure seller context is set before opening object type
    if (activeSellerId !== sellerId) openSeller(sellerId)
    openObjectType(categoryKey)
  }, [activeSellerId, openSeller, openObjectType])

  return (
    <Tooltip.Provider delayDuration={300}>
      <div className="flex flex-col h-full w-full">

        {/* ── Header ── */}
        <div className={cn(
          'flex items-center h-12 flex-shrink-0 border-b border-border px-2 gap-1',
          !leftOpen && 'justify-center',
        )}>
          {leftOpen && (
            <span className="flex-1 text-sm font-semibold text-sidebar-foreground px-1 truncate select-none">
              ICP Search
            </span>
          )}
          <TipButton
            tip={leftOpen ? 'Collapse sidebar' : 'Expand sidebar'}
            collapsed={!leftOpen}
            onClick={toggleSidebar}
          >
            {leftOpen
              ? <PanelLeftClose size={16} />
              : <PanelLeftOpen  size={16} />}
          </TipButton>
        </div>

        {/* ── Nav buttons ── */}
        <div className="flex flex-col gap-0.5 p-2 border-b border-border">
          <NavButton
            icon={<MessageSquare size={15} />}
            label="Chat"
            collapsed={!leftOpen}
            active={mainMode === 'chat'}
            onClick={openChat}
          />
          <NavButton
            icon={<Search size={15} />}
            label="Search"
            collapsed={!leftOpen}
            active={false}
            onClick={() => {}} // Block 7
          />
        </div>

        {/* ── Seller tree ── */}
        <div className="flex-1 overflow-y-auto py-2">
          {sellers.loading && (
            <div className={cn(
              'flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground',
              !leftOpen && 'justify-center px-0',
            )}>
              <Loader2 size={13} className="animate-spin flex-shrink-0" />
              {leftOpen && 'Loading…'}
            </div>
          )}

          {sellers.error && leftOpen && (
            <p className="px-3 py-2 text-xs text-destructive">{sellers.error}</p>
          )}

          {sellers.data.map((seller) => (
            <SellerEntry
              key={seller.id}
              seller={seller}
              collapsed={!leftOpen}
              expanded={expandedIds.has(seller.id)}
              active={activeSellerId === seller.id}
              activeObjectType={activeSellerId === seller.id ? activeObjectType : null}
              onToggleExpand={() => toggleExpanded(seller.id)}
              onSellerClick={() => handleSellerClick(seller)}
              onCategoryClick={(cat) => handleCategoryClick(seller.id, cat)}
            />
          ))}

          {!sellers.loading && sellers.data.length === 0 && !sellers.error && leftOpen && (
            <p className="px-3 py-4 text-xs text-muted-foreground text-center">
              No sellers yet
            </p>
          )}
        </div>

        {/* ── Footer ── */}
        <div className={cn('flex-shrink-0 border-t border-border p-2 flex flex-col gap-0.5')}>
          {currentUser?.is_admin && (
            <NavButton
              icon={<ShieldCheck size={15} />}
              label="Admin"
              collapsed={!leftOpen}
              active={false}
              onClick={() => window.location.href = '/admin'}
            />
          )}
          <NavButton
            icon={<Plus size={15} />}
            label="Add Seller"
            collapsed={!leftOpen}
            active={false}
            onClick={() => setAddSellerOpen(true)}
          />
        </div>

      </div>

      <AddSellerDialog
        open={addSellerOpen}
        onClose={() => setAddSellerOpen(false)}
      />
    </Tooltip.Provider>
  )
}

// ── SellerEntry ───────────────────────────────────────────────────────────────

function SellerEntry({
  seller, collapsed, expanded, active, activeObjectType,
  onToggleExpand, onSellerClick, onCategoryClick,
}) {
  const initial = (seller.name || '?')[0].toUpperCase()

  if (collapsed) {
    // Icon rail: show avatar only with tooltip
    return (
      <WithTooltip tip={seller.name} side="right">
        <button
          onClick={onSellerClick}
          className={cn(
            'flex items-center justify-center w-8 h-8 mx-auto my-0.5 rounded-md text-xs font-semibold',
            'transition-colors',
            active
              ? 'bg-primary text-primary-foreground'
              : 'bg-sidebar-accent text-sidebar-foreground hover:bg-accent hover:text-accent-foreground',
          )}
        >
          {initial}
        </button>
      </WithTooltip>
    )
  }

  return (
    <Collapsible.Root open={expanded} onOpenChange={onToggleExpand}>
      {/* Seller row */}
      <div className={cn(
        'group flex items-center rounded-md mx-1 transition-colors',
        active && activeObjectType === null
          ? 'bg-accent text-accent-foreground'
          : 'hover:bg-sidebar-accent',
      )}>
        {/* Expand chevron */}
        <Collapsible.Trigger asChild>
          <button
            className="flex-shrink-0 p-1 rounded text-sidebar-foreground/40 hover:text-sidebar-foreground transition-colors"
            aria-label={expanded ? 'Collapse' : 'Expand'}
            onClick={(e) => e.stopPropagation()}
          >
            <ChevronRight
              size={13}
              className={cn('transition-transform duration-150', expanded && 'rotate-90')}
            />
          </button>
        </Collapsible.Trigger>

        {/* Seller name */}
        <button
          onClick={onSellerClick}
          className="flex-1 flex items-center gap-1.5 min-w-0 py-1.5 pr-2 text-sm text-sidebar-foreground"
        >
          <Briefcase size={13} className="flex-shrink-0 text-sidebar-foreground/50" />
          <span className="truncate">{seller.name}</span>
        </button>
      </div>

      {/* Sub-categories */}
      <Collapsible.Content className="overflow-hidden data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0">
        <div className="ml-5 border-l border-border pl-2 mt-0.5 mb-1">
          {CATEGORIES.map((cat) => (
            <CategoryRow
              key={cat.key}
              cat={cat}
              active={active && activeObjectType === cat.key}
              onClick={() => onCategoryClick(cat.key)}
            />
          ))}
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}

// ── CategoryRow ───────────────────────────────────────────────────────────────

function CategoryRow({ cat, active, onClick }) {
  const Icon = cat.icon
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-2 w-full rounded-md px-2 py-1 text-xs transition-colors',
        active
          ? 'bg-accent text-accent-foreground font-medium'
          : 'text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground',
      )}
    >
      <Icon size={12} className="flex-shrink-0" />
      <span>{cat.label}</span>
    </button>
  )
}

// ── NavButton ─────────────────────────────────────────────────────────────────

function NavButton({ icon, label, collapsed, active, onClick }) {
  const btn = (
    <button
      onClick={onClick}
      title={collapsed ? label : undefined}
      className={cn(
        'flex items-center gap-2 rounded-md w-full transition-colors text-sm',
        'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground',
        active && 'bg-sidebar-accent text-sidebar-foreground font-medium',
        collapsed ? 'justify-center p-1.5' : 'px-2 py-1.5',
      )}
    >
      {icon}
      {!collapsed && <span className="truncate">{label}</span>}
    </button>
  )

  if (collapsed) {
    return <WithTooltip tip={label} side="right">{btn}</WithTooltip>
  }
  return btn
}

// ── TipButton ─────────────────────────────────────────────────────────────────

function TipButton({ tip, collapsed, onClick, children }) {
  const btn = (
    <button
      onClick={onClick}
      className="p-1.5 rounded-md hover:bg-sidebar-accent text-sidebar-foreground/60 hover:text-sidebar-foreground transition-colors"
      aria-label={tip}
    >
      {children}
    </button>
  )
  if (collapsed) return <WithTooltip tip={tip} side="right">{btn}</WithTooltip>
  return btn
}

// ── WithTooltip ───────────────────────────────────────────────────────────────

function WithTooltip({ tip, side = 'right', children }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side={side}
          sideOffset={6}
          className="z-50 rounded-md bg-popover text-popover-foreground px-2 py-1 text-xs shadow-md border border-border animate-in fade-in-0 zoom-in-95"
        >
          {tip}
          <Tooltip.Arrow className="fill-popover" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}
