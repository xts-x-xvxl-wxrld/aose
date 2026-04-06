import { describe, expect, test } from 'vitest'

import { ACTION_CATALOG, getVisibleActions } from './catalog'

describe('ACTION_CATALOG', () => {
  test('every action has the expected shape', () => {
    for (const action of ACTION_CATALOG) {
      expect(action.id).toBeTruthy()
      expect(action.label).toBeTruthy()
      expect(typeof action.condition).toBe('function')
      expect(typeof action.prompt).toBe('string')
    }
  })
})

describe('getVisibleActions', () => {
  test('shows account search when seller and icp context are present', () => {
    const actions = getVisibleActions({ hasSellerProfile: true, hasIcpProfile: true })
    expect(actions.map((action) => action.id)).toContain('search_accounts')
  })

  test('hides account search until icp context exists', () => {
    const actions = getVisibleActions({ hasSellerProfile: true, hasIcpProfile: false })
    expect(actions.map((action) => action.id)).not.toContain('search_accounts')
  })

  test('shows research and contact search when an account is selected', () => {
    const actions = getVisibleActions({ hasSellerProfile: true, hasSelectedAccount: true })
    expect(actions.map((action) => action.id)).toEqual(['research_account', 'find_contacts'])
  })

  test('shows status action when a workflow is already active', () => {
    const actions = getVisibleActions({ activeWorkflow: 'account_search' })
    expect(actions.map((action) => action.id)).toContain('check_status')
  })

  test('compact mode truncates the prompt list', () => {
    const actions = getVisibleActions({
      hasSellerProfile: true,
      hasIcpProfile: true,
      hasSelectedAccount: true,
      activeWorkflow: 'account_search',
    }, { compact: true })

    expect(actions).toHaveLength(3)
  })
})
