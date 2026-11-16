import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import InterviewRoom from './routes/interview/InterviewRoom';

// Candidates only ever load the interview room; keep the admin console,
// supervisor view and demo page out of their initial download.
const Landing = lazy(() => import('./routes/interview/Landing'));
const SupervisorRoom = lazy(() => import('./routes/interview/SupervisorRoom'));
const Dashboard = lazy(() => import('./routes/admin/Dashboard'));
const Jobs = lazy(() => import('./routes/admin/Jobs'));
const Questions = lazy(() => import('./routes/admin/Questions'));
const Candidates = lazy(() => import('./routes/admin/Candidates'));
const Records = lazy(() => import('./routes/admin/Records'));
const ReportDetail = lazy(() => import('./routes/admin/ReportDetail'));
const Settings = lazy(() => import('./routes/admin/Settings'));

function RouteFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center text-sm text-muted" role="status">
      加载中…
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/" element={<Navigate to="/interview" replace />} />
        <Route path="/interview" element={<InterviewRoom />} />
        <Route path="/interview/orb" element={<Landing />} />
        <Route path="/supervise" element={<SupervisorRoom />} />
        <Route path="/admin" element={<Dashboard />} />
        <Route path="/admin/jobs" element={<Jobs />} />
        <Route path="/admin/questions" element={<Questions />} />
        <Route path="/admin/candidates" element={<Candidates />} />
        <Route path="/admin/records" element={<Records />} />
        <Route path="/admin/reports/:token" element={<ReportDetail />} />
        <Route path="/admin/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/interview" replace />} />
      </Routes>
    </Suspense>
  );
}
