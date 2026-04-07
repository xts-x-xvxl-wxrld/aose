import React from 'react'

export default function App() {
  const AppRouter = React.lazy(() => import('@/app/AppRouter'))

  return (
    <React.Suspense fallback={null}>
      <AppRouter />
    </React.Suspense>
  )
}
