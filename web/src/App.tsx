import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Uebersicht } from './pages/Uebersicht'

/* Ausschliesslich die Routentabelle. Das Layout ist Elternroute mit <Outlet />,
   damit Navigation und Kopfzeile beim Seitenwechsel nicht neu montiert werden.
   Weitere Seiten kommen mit den Meilensteinen (docs/roadmap.md). */
export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Uebersicht />} />
        <Route path="*" element={<div className="content"><div className="empty">Seite nicht gefunden.</div></div>} />
      </Route>
    </Routes>
  )
}
