import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import { AuthProvider } from './auth/AuthContext'
import { RequireAuth } from './auth/RequireAuth'
import { AdminLayout } from './components/AdminLayout'
import { AdminWorkbenchLayout } from './components/AdminWorkbenchLayout'
import { ReviewWorkbenchLayout } from './components/ReviewWorkbenchLayout'
import { HomeRedirect } from './components/HomeRedirect'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { ExportAudioPage } from './pages/ExportAudioPage'
import { ExportFlaggedPage } from './pages/ExportFlaggedPage'
import { ExportResponsesPage } from './pages/ExportResponsesPage'
import { LoginPage } from './pages/LoginPage'
import { ParticipantDetailPage } from './pages/ParticipantDetailPage'
import { ParticipantsPage } from './pages/ParticipantsPage'
import { PassagesListPage } from './pages/PassagesListPage'
import { QaItemDetailPage } from './pages/QaItemDetailPage'
import { QaItemsListPage } from './pages/QaItemsListPage'
import { RecordPage } from './pages/RecordPage'
import { ReviewQaPage } from './pages/ReviewQaPage'
import { ReviewResponsePage } from './pages/ReviewResponsePage'
import { SystemLanguagesPage } from './pages/SystemLanguagesPage'

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <AdminLayout />
              </RequireAuth>
            }
          >
            <Route index element={<HomeRedirect />} />
            <Route
              element={
                <RequireAuth roles={['admin']}>
                  <AdminWorkbenchLayout />
                </RequireAuth>
              }
            >
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="passages" element={<PassagesListPage />} />
              <Route path="qa-items" element={<Navigate to="/qa-items/list" replace />} />
              <Route path="qa-items/add" element={<Navigate to="/qa-items/list" replace />} />
              <Route path="qa-items/add-passages" element={<Navigate to="/passages" replace />} />
              <Route path="qa-items/list" element={<QaItemsListPage />} />
              <Route path="qa-items/passages" element={<Navigate to="/passages" replace />} />
              <Route path="qa-items/:qaItemId" element={<QaItemDetailPage />} />
              <Route path="participants" element={<ParticipantsPage />} />
              <Route path="participants/:participantId" element={<ParticipantDetailPage />} />
              <Route path="export/audio" element={<ExportAudioPage />} />
              <Route path="export/responses" element={<ExportResponsesPage />} />
              <Route path="export/flagged" element={<ExportFlaggedPage />} />
            </Route>
            <Route
              element={
                <RequireAuth roles={['admin', 'expert']}>
                  <ReviewWorkbenchLayout />
                </RequireAuth>
              }
            >
              <Route path="review-response" element={<ReviewResponsePage />} />
              <Route path="review-qa" element={<ReviewQaPage />} />
              <Route path="record" element={<RecordPage />} />
            </Route>
            <Route
              path="system-languages"
              element={
                <RequireAuth roles={['admin', 'expert']}>
                  <SystemLanguagesPage />
                </RequireAuth>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
