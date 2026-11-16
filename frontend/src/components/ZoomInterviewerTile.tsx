import StateVideoInterviewerTile from './StateVideoInterviewerTile';
import type { AvatarStateCommand } from '../lib/avatarStateController';

interface ZoomInterviewerTileProps {
  speaking?: boolean;
  active?: boolean;
  className?: string;
}

export default function ZoomInterviewerTile({
  speaking = false,
  active = false,
  className,
}: ZoomInterviewerTileProps) {
  const command: AvatarStateCommand = {
    state: speaking ? 'speaking' : active ? 'listening' : 'idle',
  };

  return (
    <StateVideoInterviewerTile
      command={command}
      active={active}
      className={className}
    />
  );
}
