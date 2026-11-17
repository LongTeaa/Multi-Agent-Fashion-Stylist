import React from 'react';

interface SegmentedScaleProps {
  /** Accessible name of the group; each button is announced as "<label> <level>". */
  label: string;
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  testIdPrefix?: string;
}

const LEVELS = [1, 2, 3, 4, 5] as const;

/** 1–5 segmented control used for comfort and formality levels. */
export function SegmentedScale({ label, value, onChange, disabled = false, testIdPrefix }: SegmentedScaleProps) {
  return (
    <div className="grid grid-cols-5 gap-1 rounded-xl bg-sunken p-1" role="group" aria-label={label}>
      {LEVELS.map((level) => (
        <button
          key={level}
          type="button"
          disabled={disabled}
          data-testid={testIdPrefix ? `${testIdPrefix}-${level}` : undefined}
          aria-pressed={value === level}
          aria-label={`${label} ${level}`}
          onClick={() => onChange(level)}
          className={`h-8 rounded-lg text-sm font-semibold tabular-nums transition-colors disabled:cursor-not-allowed ${
            value === level
              ? 'bg-ink text-paper'
              : value > level
              ? 'bg-surface text-ink'
              : 'text-muted hover:bg-surface hover:text-ink'
          }`}
        >
          {level}
        </button>
      ))}
    </div>
  );
}
