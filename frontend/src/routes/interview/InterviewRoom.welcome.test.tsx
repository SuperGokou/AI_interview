import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import InterviewRoom from './InterviewRoom';

const mocks = vi.hoisted(() => ({
  cameraSample: undefined as undefined | ((present: boolean | null) => void),
  cameraStop: vi.fn(),
  cameraStart: vi.fn(),
  session: {
    start: vi.fn(),
    stop: vi.fn(),
    active: false,
    videoRef: { current: null },
    micEnabled: true,
    cameraEnabled: true,
    setMicEnabled: vi.fn(),
    setCameraEnabled: vi.fn(),
    interviewerText: '',
    candidateText: '',
    integrity: 'green',
    speaking: false,
    error: '',
  },
}));

vi.mock('../../lib/personCamera', () => ({ startPersonCamera: (...args: unknown[]) => mocks.cameraStart(...args) }));

vi.mock('../../hooks/useInterviewSession', () => ({
  useInterviewSession: () => mocks.session,
}));

vi.mock('../../components/StateVideoInterviewerTile', () => ({
  default: ({ command }: { command: { state: string } }) => (
    <div data-testid="state-video-interviewer-tile" data-state={command.state} />
  ),
}));

class FakeMediaStream {
  getTracks() {
    return [];
  }
}

describe('InterviewRoom landing and avatar state videos', () => {
  beforeEach(() => {
    mocks.cameraStop.mockReset();
    mocks.cameraStart.mockReset().mockImplementation((sample) => { mocks.cameraSample = sample; return mocks.cameraStop; });
    vi.stubGlobal('MediaStream', FakeMediaStream);
    Object.defineProperty(HTMLMediaElement.prototype, 'play', {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
      configurable: true,
      value: vi.fn(),
    });

    window.history.replaceState({}, '', '/interview');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      token: 'demo-token', status: 'pending', job: { duration_minutes: 5 },
    }), {status: 200})));
    mocks.session.start.mockReset();
    mocks.session.start.mockResolvedValue(undefined);
    mocks.session.stop.mockReset();
    mocks.session.active = false;
    mocks.session.interviewerText = '';
    mocks.session.candidateText = '';
    mocks.session.error = '';
    mocks.session.speaking = false;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: undefined,
    });
  });

  test('production without a token enables greeting detection but never creates a demo session', () => {
    vi.stubEnv('DEV', false);
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } });
    render(<InterviewRoom />);
    expect(screen.getByText(/请使用专属面试链接/)).toBeInTheDocument();
    expect(screen.getByRole('link', {name: '前往后台生成面试链接'})).toHaveAttribute('href', '/admin/candidates');
    expect(screen.queryByRole('button', {name: '开始面试'})).not.toBeInTheDocument();
    expect(mocks.cameraStart).toHaveBeenCalledTimes(1);
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  test('production with a valid token starts without the demo endpoint', async () => {
    vi.stubEnv('DEV', false);
    window.history.replaceState({}, '', '/interview?token=real-token');
    const stream = new FakeMediaStream();
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {getUserMedia: vi.fn().mockResolvedValue(stream)} });
    render(<InterviewRoom />);
    await act(async () => {fireEvent.click(screen.getByRole('button', {name: '开始面试'}));});
    expect(mocks.cameraStop).toHaveBeenCalled();
    expect(mocks.session.start).toHaveBeenCalledWith('real-token', stream);
    expect(vi.mocked(fetch).mock.calls.some(([url])=>String(url).includes('demo-session'))).toBe(false);
  });

  test('renders the welcome video with embedded audio and no separate playback button', () => {
    render(<InterviewRoom />);

    expect(screen.getByLabelText('AI 面试官欢迎视频')).toHaveAttribute(
      'src',
      '/kunyao-welcome-transparent-v1.webm'
    );
    expect(screen.queryByRole('button', { name: '播放欢迎语' })).not.toBeInTheDocument();
  });

  test('starts the interview without any external avatar readiness gate', async () => {
    const stream = new FakeMediaStream();
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue(stream),
      },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url === '/api/dev/demo-session') {
          return new Response(JSON.stringify({ token: 'demo-token' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ token: 'demo-token', status: 'pending', job: { duration_minutes: 5 } }), {status: 200});
      })
    );

    render(<InterviewRoom />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '开始面试' }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mocks.session.start).toHaveBeenCalledWith('demo-token', stream);
  });

  test('returns to the landing screen and plays the ending video after ending the interview', async () => {
    mocks.session.active = true;
    mocks.session.stop.mockImplementation(() => {
      mocks.session.active = false;
    });

    render(<InterviewRoom />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '结束面试' }));
    });

    expect(mocks.session.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('AI 面试官结束语视频')).toHaveAttribute(
      'src',
      '/kunyao-ending-transparent-v1.webm'
    );
    const video = screen.getByLabelText('AI 面试官结束语视频');
    expect(video).toHaveAttribute('autoplay');
    expect(video).not.toHaveAttribute('controls');
    expect(video).not.toHaveAttribute('loop');
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    expect(screen.queryByRole('button', {name: /播放.*视频/})).not.toBeInTheDocument();
    expect(video).toHaveStyle({ filter: 'none' });
    expect(video.parentElement?.querySelector('.bottom-0')).toBeNull();
  });

  test('disables the start button after an interview has ended', async () => {
    mocks.session.active = true;
    mocks.session.stop.mockImplementation(() => {
      mocks.session.active = false;
    });

    render(<InterviewRoom />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '结束面试' }));
    });

    const endedButton = screen.getByRole('button', { name: '面试已结束' });
    expect(endedButton).toBeDisabled();

    await act(async () => {
      fireEvent.click(endedButton);
    });

    expect(mocks.session.start).not.toHaveBeenCalled();
  });
  test('does not start a silent interview when device permission is denied', async () => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError')),
    }});
    render(<InterviewRoom />);
    await act(async () => { fireEvent.click(screen.getByRole('button', {name: '开始面试'})); });
    expect(mocks.session.start).not.toHaveBeenCalled();
    expect(screen.getByText(/请允许摄像头和麦克风/)).toBeInTheDocument();
  });

  test('uses the job duration instead of a hardcoded thirty minutes', async () => {
    window.history.replaceState({}, '', '/interview?token=test-duration');
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: vi.fn().mockResolvedValue(new FakeMediaStream()),
    }});
    mocks.session.start.mockImplementation(async () => { mocks.session.active = true; });
    render(<InterviewRoom />);
    await act(async () => { fireEvent.click(screen.getByRole('button', {name: '开始面试'})); });
    expect(screen.getByText('05:00')).toBeInTheDocument();
  });

  test('waits for arrival, plays once, and only rearms after ten seconds of absence', () => {
    let now = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const sample = (present: boolean | null, t: number) => { now = t; act(() => mocks.cameraSample!(present)); };
    render(<InterviewRoom />);
    const clip = () => screen.getByLabelText('AI 面试官欢迎视频');
    expect(clip()).not.toHaveAttribute('autoplay');
    sample(true, 0);sample(true, 500);
    expect(clip()).toHaveAttribute('autoplay');
    fireEvent.ended(clip());
    expect(clip()).not.toHaveAttribute('autoplay');
    sample(true, 750);sample(true, 1000);
    expect(clip()).not.toHaveAttribute('autoplay');
    for(let t=1250;t<=11000;t+=250)sample(false,t);
    expect(clip()).not.toHaveAttribute('autoplay');
    sample(false,11250);sample(true,11500);sample(true,12000);
    expect(clip()).toHaveAttribute('autoplay');
  });
  test('plays the welcome clip muted with a hint when sound is blocked, and restarts with sound on a tap', async () => {
    // Refuse playback with sound until the visitor has interacted, like a browser does.
    let interacted = false;
    const play = vi.fn(function (this: HTMLMediaElement) {
      return this.muted || interacted ? Promise.resolve() : Promise.reject(new DOMException('', 'NotAllowedError'));
    });
    Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: play });
    let now = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    render(<InterviewRoom />);
    const clip = () => screen.getByLabelText('AI 面试官欢迎视频') as HTMLVideoElement;
    await act(async () => { mocks.cameraSample!(true); now = 500; mocks.cameraSample!(true); });

    expect(clip().muted).toBe(true); // moving silently, not frozen on the first frame
    expect(screen.getByRole('status')).toHaveTextContent('点击页面任意位置开启声音');

    interacted = true;
    await act(async () => { fireEvent.pointerDown(document.body); });
    expect(clip().muted).toBe(false);
    expect(clip().currentTime).toBe(0); // the narration starts over, with sound
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  test('the greeting can be started by hand, once, and shows no camera status', () => {
    let now = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    render(<InterviewRoom />);
    const clip = () => screen.getByLabelText('AI 面试官欢迎视频');
    expect(screen.queryByText(/摄像头/)).not.toBeInTheDocument();
    expect(clip()).not.toHaveAttribute('autoplay');

    fireEvent.click(screen.getByRole('button', { name: '播放欢迎视频' }));
    expect(clip()).toHaveAttribute('autoplay');
    expect(screen.queryByRole('button', { name: '播放欢迎视频' })).not.toBeInTheDocument();

    // Detection seeing the same visitor a moment later must not restart the clip.
    const playing = clip();
    act(() => mocks.cameraSample!(true));
    now = 600;
    act(() => mocks.cameraSample!(true));
    expect(clip()).toBe(playing);

    fireEvent.ended(clip());
    expect(screen.getByRole('button', { name: '播放欢迎视频' })).toBeInTheDocument(); // replay on request
  });

  test('ten seconds absent stops an unfinished opening; detection pauses during interview', () => {
    let now = 0;vi.spyOn(performance,'now').mockImplementation(()=>now);
    const sample=(p:boolean,t:number)=>{now=t;act(()=>mocks.cameraSample!(p));};
    const {rerender}=render(<InterviewRoom />);
    sample(true,0);sample(true,500);
    for(let t=750;t<=10750;t+=250)sample(false,t);
    expect(screen.getByLabelText('AI 面试官欢迎视频')).not.toHaveAttribute('autoplay');
    mocks.session.active=true;rerender(<InterviewRoom />);
    expect(mocks.cameraStop).toHaveBeenCalled();
    expect(screen.queryByLabelText('AI 面试官欢迎视频')).not.toBeInTheDocument();
  });

});
