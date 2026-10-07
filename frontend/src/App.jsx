import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import HandoffQueue from './pages/HandoffQueue.jsx'
import ConversationDetail from './pages/ConversationDetail.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/queue" replace />} />
        <Route path="queue" element={<HandoffQueue />} />
        <Route path="conversation/:id" element={<ConversationDetail />} />
      </Route>
    </Routes>
  )
}
