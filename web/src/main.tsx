import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { App } from './App'
import { ThemeProvider } from './components/Theme'
import { ToastProvider } from './components/Toast'
import './styles.css'

/* Verdrahtung, keine Logik. Router aussen, dann Theme, dann Toast. HashRouter statt BrowserRouter: Unter dem
   HA-Ingress kennt der Server das Pfadpraefix nicht und koennte fuer
   Unterrouten keine index.html ausliefern (D-008). Einen AuthProvider gibt es
   nicht — die Anmeldung macht der Ingress. */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <ThemeProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
)
