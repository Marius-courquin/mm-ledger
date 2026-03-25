import type { ReactNode } from 'react';

interface MetricCardProps {
  label: string;
  value: string;
  valueClassName?: string;
  sub?: string;
  icon?: ReactNode;
}

export function MetricCard({ label, value, valueClassName, sub, icon }: MetricCardProps) {
  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] p-4 flex flex-col gap-2">
      <span className="text-xs font-medium text-mm-text-muted">{label}</span>
      <span className={`tabular-nums font-bold ${valueClassName ?? 'text-2xl text-mm-text'}`}>
        {value}
      </span>
      {sub && (
        <span className="flex items-center gap-1 text-[11px] text-mm-text-muted">
          {icon}
          {sub}
        </span>
      )}
    </div>
  );
}
