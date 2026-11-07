import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import GlobalErrorBoundary from './components/GlobalErrorBoundary.js'
import './theme-polish.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <GlobalErrorBoundary><App /></GlobalErrorBoundary>
  </StrictMode>,
)
