#!/bin/sh
set -eu

echo "[frontend] running preflight checks"
node scripts/prestart.mjs

echo "[frontend] installing dependencies"
npm install

echo "[frontend] starting vite"
exec npm run dev -- --host 0.0.0.0 --port "${PORT:-5173}"
