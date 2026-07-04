import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/globals.css'
import App from './App.tsx'
import { initAnalytics } from './lib/analytics'

// Cookieless analytics — inert unless VITE_PLAUSIBLE_DOMAIN is set (see lib/analytics.ts).
initAnalytics()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
