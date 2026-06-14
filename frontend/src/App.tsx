import { Navigate, Route, Routes } from 'react-router-dom';
import InterviewRoom from './routes/interview/InterviewRoom';
import Landing from './routes/interview/Landing';
import Dashboard from './routes/admin/Dashboard';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/interview" replace />} />
      <Route path="/interview" element={<InterviewRoom />} />
      <Route path="/interview/orb" element={<Landing />} />
      <Route path="/admin" element={<Dashboard />} />
    </Routes>
  );
}
