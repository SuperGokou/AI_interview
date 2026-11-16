import { type ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'ghost' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-cyan text-[#06222B] shadow-glow-cyan hover:brightness-110 font-semibold',
  ghost:
    'bg-transparent text-muted border border-border hover:border-cyan hover:text-text',
  danger:
    'bg-red/10 text-red border border-red/30 hover:bg-red/20',
};

export default function Button({
  variant = 'primary',
  className = '',
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={[
        'inline-flex items-center justify-center gap-2',
        'rounded-xl px-5 py-2.5 text-sm font-medium',
        'transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan focus-visible:ring-offset-2 focus-visible:ring-offset-bg',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
        variantClasses[variant],
        className,
      ].join(' ')}
      disabled={disabled}
      {...rest}
    >
      {children}
    </button>
  );
}
