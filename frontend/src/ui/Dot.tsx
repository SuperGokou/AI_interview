interface DotProps {
  size?: number;
  color: string;
  glow?: boolean;
}

export default function Dot({ size = 8, color, glow = false }: DotProps) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: '50%',
        backgroundColor: color,
        flexShrink: 0,
        boxShadow: glow ? `0 0 8px ${color}` : undefined,
      }}
      aria-hidden="true"
    />
  );
}
