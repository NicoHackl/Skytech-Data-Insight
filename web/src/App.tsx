import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Uebersicht } from './pages/Uebersicht'
import { Sensoren } from './pages/Sensoren'
import { SensorenNeu } from './pages/SensorenNeu'
import { SensorBearbeiten } from './pages/SensorBearbeiten'

/* Ausschliesslich die Routentabelle. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden.
   Weitere Seiten kommen mit den Meilensteinen (docs/roadmap.md). */
export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Uebersicht />} />
        <Route path="/sensoren" element={<Sensoren />} />
        <Route path="/sensoren/neu" element={<SensorenNeu />} />
        <Route path="/sensoren/:id" element={<SensorBearbeiten />} />
        <Route path="*" element={<div className="content"><div className="empty">Seite nicht gefunden.</div></div>} />
      </Route>
    </Routes>
  )
}
