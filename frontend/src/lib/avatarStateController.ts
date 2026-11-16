import { useCallback, useEffect, useMemo, useState } from 'react';

export type AvatarState = 'idle' | 'greeting' | 'listening' | 'speaking' | 'thinking';

export interface AvatarStateCommand {
  state: AvatarState;
  text?: string;
  audioUrl?: string;
  videoUrl?: string;
  intent?: string;
  tone?: string;
}

type AvatarStateListener = (command: AvatarStateCommand) => void;

/**
 * Coordinates the AI interviewer visual state independently from the renderer.
 *
 * The controller is intentionally renderer-agnostic. Today it selects a
 * pre-rendered state video. Later, the same command shape can point `videoUrl`
 * at a per-turn LivePortrait or LiveAvatar clip without changing interview
 * flow code.
 */
export class AvatarStateController {
  private currentCommand: AvatarStateCommand = { state: 'idle' };

  private readonly listeners = new Set<AvatarStateListener>();

  get command(): AvatarStateCommand {
    return this.currentCommand;
  }

  setAvatarState(state: AvatarState, patch: Omit<AvatarStateCommand, 'state'> = {}) {
    this.setCommand({ state, ...patch });
  }

  setCommand(command: AvatarStateCommand) {
    this.currentCommand = command;
    this.listeners.forEach((listener) => listener(command));
  }

  subscribe(listener: AvatarStateListener) {
    this.listeners.add(listener);
    listener(this.currentCommand);
    return () => {
      this.listeners.delete(listener);
    };
  }
}

/**
 * Creates a React binding for AvatarStateController.
 *
 * Returns:
 *   The stable controller instance and the latest command emitted by it.
 */
export function useAvatarStateController(initialState: AvatarState = 'idle') {
  const controller = useMemo(() => {
    const instance = new AvatarStateController();
    instance.setAvatarState(initialState);
    return instance;
  }, [initialState]);

  const [command, setCommand] = useState<AvatarStateCommand>(controller.command);

  useEffect(() => controller.subscribe(setCommand), [controller]);

  const setAvatarState = useCallback(
    (state: AvatarState, patch: Omit<AvatarStateCommand, 'state'> = {}) => {
      controller.setAvatarState(state, patch);
    },
    [controller]
  );

  return { controller, command, setAvatarState };
}
