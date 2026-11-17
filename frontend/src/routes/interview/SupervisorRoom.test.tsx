import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import SupervisorRoom from './SupervisorRoom';

const mocks = vi.hoisted(() => ({
  getSupervisorSession: vi.fn(),
  listSupervisorTranscripts: vi.fn(),
  supervisorFrame: vi.fn(),
}));

vi.mock('../../lib/api', () => ({ api: mocks }));

const SESSION = {
  supervisor_token: 'sup',
  label: '监督员 1',
  session_token: '',
  status: 'active',
  candidate_name: '张三',
  job: { title: 'ML 算法工程师', language: 'zh', duration_minutes: 20, interviewer_voice: 'Tina' },
  supervisors: [
    { label: '监督员 1', is_current: true },
    { label: '监督员 2', is_current: false },
  ],
};

function feed(status: string) {
  return {
    status,
    live: status !== 'pending',
    transcripts: [{ role: 'interviewer', text: '请介绍一个你做过的项目。', ts: '2026-11-17T10:00:00Z' }],
    integrity_level: 'red',
    events: [
      { kind: 'gaze_off_screen', severity: 'medium', evidence: '一直低着头', ts: '2026-11-17T10:00:05Z' },
      { kind: 'phone', severity: 'high', evidence: '手里拿着手机', ts: '2026-11-17T10:00:20Z' },
    ],
  };
}

describe('SupervisorRoom', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/supervisor?token=sup');
    URL.createObjectURL = vi.fn(() => 'blob:frame');
    URL.revokeObjectURL = vi.fn();
    mocks.getSupervisorSession.mockResolvedValue(SESSION);
    mocks.supervisorFrame.mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  test('shows the candidate live, what proctoring found, and the conversation', async () => {
    mocks.listSupervisorTranscripts.mockResolvedValue(feed('active'));
    render(<SupervisorRoom />);

    const picture = await screen.findByAltText('张三的实时画面');
    expect(picture).toHaveAttribute('src', 'blob:frame');
    expect(mocks.supervisorFrame).toHaveBeenCalledWith('sup');

    expect(screen.getByText('高风险')).toBeInTheDocument();
    expect(screen.getByText('面试进行中')).toBeInTheDocument();
    expect(screen.getByText('监督员 1 · 另有 1 位监督员')).toBeInTheDocument();
    expect(screen.getByText('请介绍一个你做过的项目。')).toBeInTheDocument();

    // Newest finding first.
    const findings = screen.getAllByRole('listitem').map((item) => item.textContent ?? '');
    expect(findings[0]).toContain('画面中出现手机');
    expect(findings[1]).toContain('视线长时间离开屏幕');
  });

  test('does not ask for a picture once the interview is over', async () => {
    mocks.getSupervisorSession.mockResolvedValue({ ...SESSION, status: 'done' });
    mocks.listSupervisorTranscripts.mockResolvedValue(feed('done'));
    render(<SupervisorRoom />);

    expect(await screen.findAllByText('面试已结束')).not.toHaveLength(0);
    expect(mocks.supervisorFrame).not.toHaveBeenCalled();
    expect(screen.queryByAltText('张三的实时画面')).not.toBeInTheDocument();
  });
});
