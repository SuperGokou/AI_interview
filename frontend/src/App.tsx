import { Navigate, Route, Routes } from 'react-router-dom';
import InterviewRoom from './routes/interview/InterviewRoom';
import Landing from './routes/interview/Landing';
import Dashboard from './routes/admin/Dashboard';
import Jobs from './routes/admin/Jobs';
import Questions from './routes/admin/Questions';
import Candidates from './routes/admin/Candidates';
import Records from './routes/admin/Records';
import ReportDetail from './routes/admin/ReportDetail';
import Settings from './routes/admin/Settings';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/interview" replace />} />
      <Route path="/interview" element={<InterviewRoom />} />
      <Route path="/interview/orb" element={<Landing />} />
      <Route path="/admin" element={<Dashboard />} />
      <Route path="/admin/jobs" element={<Jobs />} />
      <Route path="/admin/questions" element={<Questions />} />
      <Route path="/admin/candidates" element={<Candidates />} />
      <Route path="/admin/records" element={<Records />} />
      <Route path="/admin/reports/:token" element={<ReportDetail />} />
      <Route path="/admin/settings" element={<Settings />} />
    </Routes>
  );
}
