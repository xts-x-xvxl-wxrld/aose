import { UserManager, WebStorageStateStore } from 'oidc-client-ts'

import { isZitadelConfigured, zitadelConfig } from '@/features/auth/authConfig'

let userManager = null

function getUserManager() {
  if (!isZitadelConfigured) return null
  if (userManager) return userManager

  userManager = new UserManager({
    authority: zitadelConfig.issuer,
    client_id: zitadelConfig.clientId,
    redirect_uri: zitadelConfig.redirectUri,
    post_logout_redirect_uri: zitadelConfig.postLogoutRedirectUri,
    response_type: 'code',
    scope: zitadelConfig.scope,
    loadUserInfo: true,
    automaticSilentRenew: false,
    userStore: new WebStorageStateStore({ store: window.localStorage }),
    extraQueryParams: zitadelConfig.audience
      ? { audience: zitadelConfig.audience }
      : undefined,
  })

  return userManager
}

export async function getStoredAuthUser() {
  const manager = getUserManager()
  if (!manager) return null
  return manager.getUser()
}

export async function signIn(returnTo = '/workspace') {
  const manager = getUserManager()
  if (!manager) {
    throw new Error('Zitadel auth is not configured for this frontend.')
  }
  await manager.signinRedirect({
    state: { returnTo },
  })
}

export async function completeSignIn() {
  const manager = getUserManager()
  if (!manager) {
    throw new Error('Zitadel auth is not configured for this frontend.')
  }
  return manager.signinRedirectCallback()
}

export async function signOut() {
  const manager = getUserManager()
  if (!manager) return
  const user = await manager.getUser()
  await manager.removeUser()
  await manager.signoutRedirect({
    id_token_hint: user?.id_token,
  })
}

export async function clearStoredAuthUser() {
  const manager = getUserManager()
  if (!manager) return
  await manager.removeUser()
}
