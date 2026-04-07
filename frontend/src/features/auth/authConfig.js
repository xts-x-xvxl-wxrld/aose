function trimTrailingSlash(value) {
  return typeof value === 'string' ? value.trim().replace(/\/$/, '') : ''
}

export const zitadelConfig = {
  issuer: trimTrailingSlash(import.meta.env?.VITE_ZITADEL_ISSUER || ''),
  clientId: (import.meta.env?.VITE_ZITADEL_CLIENT_ID || '').trim(),
  audience: (import.meta.env?.VITE_ZITADEL_AUDIENCE || '').trim(),
  scope: (import.meta.env?.VITE_ZITADEL_SCOPE || 'openid profile email').trim(),
  redirectUri: (
    import.meta.env?.VITE_ZITADEL_REDIRECT_URI ||
    `${window.location.origin}/auth/callback`
  ).trim(),
  postLogoutRedirectUri: (
    import.meta.env?.VITE_ZITADEL_POST_LOGOUT_REDIRECT_URI ||
    `${window.location.origin}/login`
  ).trim(),
}

export const isZitadelConfigured = Boolean(
  zitadelConfig.issuer &&
  zitadelConfig.clientId,
)
