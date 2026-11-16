import { type ChangeEvent, useId } from 'react';

interface FieldProps {
  label: string;
  value: string;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  type?: string;
}

export default function Field({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: FieldProps) {
  const id = useId();

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="text-sm font-medium text-muted"
      >
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        style={{ background: '#0E1525' }}
        className="rounded-xl border border-border px-4 py-3 text-text text-sm
          placeholder:text-muted
          focus:outline-none focus:border-cyan focus:ring-1 focus:ring-cyan
          transition-colors duration-150"
      />
    </div>
  );
}
