import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import StateVideoInterviewerTile from './StateVideoInterviewerTile';

vi.mock('./NeuralInterviewer', () => ({ default: () => <div data-testid="audio-driven-mouth" /> }));

const command = { state: 'idle' as const };
const config = {
  fps: 25,
  delaySeconds: 1.2,
  frame: { width: 1672, height: 940 },
  patch: { x: 617, y: 0, width: 514, height: 504 },
};

describe('StateVideoInterviewerTile', () => {
  it('uses the audio-driven mouth when realtime rendering is off', () => {
    render(<StateVideoInterviewerTile command={command} mouthFrameRef={{ current: null }} />);
    expect(screen.getByTestId('audio-driven-mouth')).toBeInTheDocument();
  });

  it('shows the still portrait under the rendered head when realtime rendering is on', () => {
    const { container } = render(
      <StateVideoInterviewerTile command={command} mouthConfig={config} mouthFrameRef={{ current: null }} />
    );
    expect(screen.queryByTestId('audio-driven-mouth')).not.toBeInTheDocument();
    expect(screen.getByAltText('坤曜 AI 面试官')).toHaveAttribute('src', '/zoom-interviewer-listening.png');
    const canvas = container.querySelector('canvas');
    expect(canvas).toHaveAttribute('width', '1672');
    expect(canvas).toHaveAttribute('height', '940');
  });
});
