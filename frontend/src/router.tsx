import { createBrowserRouter } from 'react-router-dom'
import { Layout } from './components/Layout'
import { DashboardPage } from './pages/DashboardPage'
import { NewAnalysisPage } from './pages/NewAnalysisPage'
import { AnalysisResultPage } from './pages/AnalysisResultPage'
import { FixSuggestionPage } from './pages/FixSuggestionPage'
import { VerificationPage } from './pages/VerificationPage'
import { ReportPage } from './pages/ReportPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'analysis/new', element: <NewAnalysisPage /> },
      { path: 'analysis/:id/results', element: <AnalysisResultPage /> },
      { path: 'analysis/:id/fix', element: <FixSuggestionPage /> },
      { path: 'analysis/:id/verify', element: <VerificationPage /> },
      { path: 'analysis/:id/report', element: <ReportPage /> },
    ],
  },
])
