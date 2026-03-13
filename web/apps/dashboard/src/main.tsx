import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './main.css'
import '@xterm/xterm/css/xterm.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
