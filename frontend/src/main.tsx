/**
 * Main Entry Point
 * Initializes the React application and mounts it to the DOM
 * Wraps the App component with React StrictMode for development checks
 * Requirements: All requirements
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Mount the application to the root element
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
