import type { ReactNode } from 'react';

interface AccountRowProps {
  name: string;
  subtitle: string;
  balance: string;
  perf: string;
  iconBg: string;
  icon: ReactNode;
}

export function AccountRow({ name, subtitle, balance, perf, iconBg, icon }: AccountRowProps) {
  return (
    <div className="flex items-center gap-3 px-5 py-3 border-b border-mm-border">
      {/* Icon */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${iconBg}`}
      >
        {icon}
      </div>

      {/* Info */}
      <div className="flex flex-col flex-1 min-w-0">
        <span className="text-sm font-medium text-mm-text truncate">{name}</span>
        <span className="text-[11px] text-mm-text-muted">{subtitle}</span>
      </div>

      {/* Balance + Perf */}
      <div className="flex flex-col items-end shrink-0">
        <span className="text-sm font-semibold text-mm-text tabular-nums">{balance}</span>
        <span className="text-[11px] font-medium text-mm-gain tabular-nums">{perf}</span>
      </div>
    </div>
  );
}
