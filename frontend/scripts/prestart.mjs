import fs from 'node:fs'

const requiredFiles = [
  'package.json',
  'index.html',
  'vite.config.js',
  'src/main.jsx',
  'src/App.jsx',
]

for (const file of requiredFiles) {
  if (!fs.existsSync(file)) {
    console.error(`[frontend] missing required file: ${file}`)
    process.exit(1)
  }
}

const apiBaseUrl = process.env.VITE_API_BASE_URL || '/api/v1'
if (!apiBaseUrl.startsWith('/')) {
  console.error('[frontend] VITE_API_BASE_URL must start with "/" for the Vite proxy setup')
  process.exit(1)
}

const backendTarget = (process.env.VITE_DEV_PROXY_TARGET || 'http://api:8000').replace(/\/$/, '')
const healthUrl = `${backendTarget}/api/v1/healthz`

for (let attempt = 1; attempt <= 15; attempt += 1) {
  try {
    const response = await fetch(healthUrl)
    if (response.ok) {
      console.log(`[frontend] backend health check passed on attempt ${attempt}`)
      console.log('[frontend] preflight checks passed')
      process.exit(0)
    }

    console.log(`[frontend] backend health check returned ${response.status} on attempt ${attempt}`)
  } catch (error) {
    console.log(`[frontend] waiting for backend on attempt ${attempt}/15: ${error.message}`)
  }

  await new Promise((resolve) => setTimeout(resolve, 2000))
}

console.error(`[frontend] backend health check failed: ${healthUrl}`)
process.exit(1)
