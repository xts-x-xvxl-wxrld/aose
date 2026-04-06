export const ACTION_CATALOG = [
  {
    id: 'search_accounts',
    label: 'Search Accounts',
    condition: (ctx) => ctx.hasSellerProfile && ctx.hasIcpProfile,
    prompt: 'Find companies matching my ICP.',
  },
  {
    id: 'research_account',
    label: 'Research Account',
    condition: (ctx) => ctx.hasSellerProfile && ctx.hasSelectedAccount,
    prompt: 'Research this account.',
  },
  {
    id: 'find_contacts',
    label: 'Find Contacts',
    condition: (ctx) => ctx.hasSellerProfile && ctx.hasSelectedAccount,
    prompt: 'Find contacts for this account.',
  },
  {
    id: 'check_status',
    label: 'Check Status',
    condition: (ctx) => Boolean(ctx.activeWorkflow),
    prompt: 'What is the status of the current workflow?',
  },
]

export function getVisibleActions(ctx, { compact = false } = {}) {
  const visible = ACTION_CATALOG.filter((action) => action.condition(ctx))
  return compact ? visible.slice(0, 3) : visible
}
