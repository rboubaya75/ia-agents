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
import { loadRuntimeConfig } from './lib/runtimeConfig'

// La configuration d'exécution est chargée avant le montage (V2-LLD-010 §15.1) : les
// bornes client doivent être alignées sur les bornes serveur dès le premier appel, et non
// figées dans le bundle. Un fichier absent n'empêche pas le démarrage — les défauts
// s'appliquent et l'écart est journalisé.
void loadRuntimeConfig().finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
