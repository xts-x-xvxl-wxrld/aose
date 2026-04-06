import React from 'react'
import { ChevronRight } from 'lucide-react'
import { useUIStore } from '@/stores/uiStore'
import SellersTable from '@/workspace/views/SellersTable'
import SellerOverview from '@/workspace/views/SellerOverview'
import ObjectTable from '@/workspace/views/ObjectTable'
import RecordDetail from '@/workspace/views/RecordDetail'

const DEPTH_LABELS = {
  'sellers-table':  'Sellers',
  'seller-overview': null,        // replaced by seller name below
  'object-table':   null,         // replaced by type label
  'record-detail':  null,
}

const TYPE_LABELS = { icps: 'ICPs', accounts: 'Accounts', contacts: 'Contacts' }

export default function ObjectViewer() {
  const depth          = useUIStore((s) => s.objectViewerDepth)
  const activeSellerId = useUIStore((s) => s.activeSellerId)
  const activeType     = useUIStore((s) => s.activeObjectType)
  const activeRecordId = useUIStore((s) => s.activeRecordId)
  const navigateBack   = useUIStore((s) => s.navigateBack)
  const openChat       = useUIStore((s) => s.openChat)

  // Breadcrumb segments
  const crumbs = buildCrumbs(depth, activeType)

  return (
    <div className="flex flex-col h-full">
      {/* ── Header / Breadcrumb ── */}
      <div className="flex items-center h-12 px-4 border-b border-border flex-shrink-0 gap-2">
        {depth !== 'sellers-table' && (
          <button
            onClick={navigateBack}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
            aria-label="Go back"
          >
            ←
          </button>
        )}
        <nav className="flex items-center gap-1 text-sm min-w-0">
          {crumbs.map((crumb, i) => (
            <React.Fragment key={i}>
              {i > 0 && <ChevronRight size={12} className="text-muted-foreground flex-shrink-0" />}
              <span className={i === crumbs.length - 1
                ? 'font-medium text-foreground truncate'
                : 'text-muted-foreground truncate'
              }>
                {crumb}
              </span>
            </React.Fragment>
          ))}
        </nav>

        <div className="ml-auto flex-shrink-0">
          <button
            onClick={openChat}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Open chat
          </button>
        </div>
      </div>

      {/* ── View ── */}
      <div className="flex-1 overflow-hidden">
        {depth === 'sellers-table'   && <SellersTable />}
        {depth === 'seller-overview' && <SellerOverview sellerId={activeSellerId} />}
        {depth === 'object-table'    && <ObjectTable sellerId={activeSellerId} objectType={activeType} />}
        {depth === 'record-detail'   && <RecordDetail sellerId={activeSellerId} objectType={activeType} recordId={activeRecordId} />}
      </div>
    </div>
  )
}

function buildCrumbs(depth, activeType) {
  switch (depth) {
    case 'sellers-table':   return ['Sellers']
    case 'seller-overview': return ['Sellers', 'Overview']
    case 'object-table':    return ['Sellers', TYPE_LABELS[activeType] || activeType]
    case 'record-detail':   return ['Sellers', TYPE_LABELS[activeType] || activeType, 'Record']
    default:                return ['Sellers']
  }
}
