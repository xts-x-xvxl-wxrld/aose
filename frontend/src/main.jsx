import React from 'react'
import ReactDOM from 'react-dom/client'
import './style.css'
import App from './App.jsx'
import AppProviders from '@/app/AppProviders'

ReactDOM.createRoot(document.getElementById('app')).render(
  <React.StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </React.StrictMode>
)
