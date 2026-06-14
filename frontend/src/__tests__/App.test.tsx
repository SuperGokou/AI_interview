import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, beforeAll, afterAll } from 'vitest';
import App from '../App';

// Stub fetch before any renders so useEffect never triggers a state update
beforeAll(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('no server'))),
  );
});
afterAll(() => {
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

test('candidate landing route renders', () => {
  renderAt('/interview');
  // InterviewRoom / Landing both render the brand
  expect(screen.getAllByText(/菜鸟庆面试/).length).toBeGreaterThan(0);
});

test('admin dashboard route renders', () => {
  renderAt('/admin');
  // AdminShell renders the brand in sidebar + mobile bar; page renders h1 "仪表盘"
  expect(screen.getAllByText(/菜鸟庆面试/).length).toBeGreaterThan(0);
  expect(screen.getByRole('heading', { name: /仪表盘/ })).toBeInTheDocument();
});
