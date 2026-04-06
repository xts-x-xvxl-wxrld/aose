import React, { useState } from 'react'
import {
  Building2, Target, Search, UserPlus, Users, Globe,
  Mail, UserSearch, Loader2,
} from 'lucide-react'
import { useUIStore } from '@/stores/uiStore'
import { useSelectionStore } from '@/stores/selectionStore'
import { getVisibleActions } from '@/workspace/actions/catalog'
import AddSellerDialog from '@/workspace/actions/dialogs/AddSellerDialog'
import AddICPDialog from '@/workspace/actions/dialogs/AddICPDialog'
import { cn } from '@/lib/utils'

const ICONS = {
  Building2, Target, Search, UserPlus, Users, Globe, Mail, UserSearch,
}

/**
 * ActionBar — horizontal row of context-filtered action buttons.
 *
 * Props:
 *   onPrompt(text)  — called when a prompt action is triggered
 *   compact         — true = sidebar layout (fewer buttons, smaller)
 *   isStreaming     — disables all buttons while agent is responding
 */
export default function ActionBar({ onPrompt, compact = false, isStreaming = false }) {
  const sellerId    = useUIStore((s) => s.activeSellerId)
  const objectType  = useUIStore((s) => s.activeObjectType)
  const selectedCount = useSelectionStore((s) => s.getSelectedCount())
  const selectedIds   = useSelectionStore((s) => s.getSelectedIds())

  const [openDialog, setOpenDialog] = useState(null) // dialog key or null

  const ctx = { sellerId, objectType, selectedCount, selectedIds }
  const actions = getVisibleActions(ctx, { compact })

  if (actions.length === 0) return null

  function handleAction(action) {
    if (isStreaming) return
    if (action.type === 'dialog') {
      setOpenDialog(action.dialog)
    } else {
      onPrompt(action.prompt(ctx))
    }
  }

  return (
    <>
      <div className={cn(
        'flex items-center gap-1.5 overflow-x-auto border-t border-border',
        compact ? 'px-2 py-1.5' : 'px-4 py-2',
        // hide scrollbar but keep scrollability
        '[&::-webkit-scrollbar]:hidden',
      )}>
        {actions.map((action) => {
          const Icon = ICONS[action.icon] || Building2
          return (
            <button
              key={action.id}
              onClick={() => handleAction(action)}
              disabled={isStreaming}
              className={cn(
                'flex items-center gap-1.5 rounded-full border border-border whitespace-nowrap',
                'text-muted-foreground hover:text-foreground hover:bg-muted transition-colors',
                'disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0',
                compact
                  ? 'text-[11px] px-2 py-0.5'
                  : 'text-xs px-2.5 py-1',
              )}
            >
              <Icon size={compact ? 10 : 12} />
              {action.label}
            </button>
          )
        })}
        {isStreaming && (
          <Loader2
            size={12}
            className={cn('animate-spin text-muted-foreground flex-shrink-0', compact ? 'ml-1' : 'ml-2')}
          />
        )}
      </div>

      {/* Dialogs — rendered outside the scrollable row */}
      <AddSellerDialog
        open={openDialog === 'AddSeller'}
        onClose={() => setOpenDialog(null)}
      />
      <AddICPDialog
        open={openDialog === 'AddICP'}
        sellerId={sellerId}
        onClose={() => setOpenDialog(null)}
      />
    </>
  )
}
