import { type ReactNode } from 'react';
import Dot from './Dot';

interface PillProps {
  children: ReactNode;
  color: string;
  bg?: string;
  dot?: boolean;
}

export default function Pill({ children, color, bg, dot = true }: PillProps) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        backgroundColor: bg ?? `${color}1A`,
        color,
        padding: '3px 10px',
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 500,
        lineHeight: 1.5,
      }}
    >
      {dot && <Dot size={6} color={color} />}
      {children}
    </span>
  );
}
