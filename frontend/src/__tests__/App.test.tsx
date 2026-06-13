import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

test('candidate landing route renders', () => {
  renderAt('/interview');
  expect(screen.getByText(/菜鸟庆面试/)).toBeInTheDocument();
});

test('admin dashboard route renders', () => {
  renderAt('/admin');
  expect(screen.getByText(/管理后台/)).toBeInTheDocument();
});
