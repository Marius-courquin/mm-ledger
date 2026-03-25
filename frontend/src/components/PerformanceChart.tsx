import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface PerformanceChartProps {
  data: { date: string; value: number }[];
  periods: string[];
  activePeriod: string;
  onPeriodChange: (period: string) => void;
}

function formatYAxis(value: number): string {
  if (value >= 1000) return `\u20AC${Math.round(value / 1000)}K`;
  return `\u20AC${value}`;
}

export function PerformanceChart({
  data,
  periods,
  activePeriod,
  onPeriodChange,
}: PerformanceChartProps) {
  return (
    <div className="bg-mm-surface border border-mm-border rounded-[12px] p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-mm-text">Portfolio Performance</h3>
        <div className="flex items-center gap-1">
          {periods.map((period) => {
            const isActive = period === activePeriod;
            return (
              <button
                key={period}
                onClick={() => onPeriodChange(period)}
                className={[
                  'rounded-[4px] px-3 py-1.5 text-xs transition-colors',
                  isActive
                    ? 'bg-mm-surface-elevated border border-mm-gold text-mm-gold font-semibold'
                    : 'border border-transparent text-mm-text-muted font-medium hover:text-mm-text-secondary',
                ].join(' ')}
              >
                {period}
              </button>
            );
          })}
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="goldGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#C9A84C" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#C9A84C" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke="#1a3d4d40"
            horizontal={true}
            vertical={false}
          />
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }}
            dy={8}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: 'rgba(226,207,234,0.5)', fontSize: 10 }}
            tickFormatter={formatYAxis}
            dx={-4}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#143a42',
              border: '1px solid #1a3d4d',
              borderRadius: 8,
              color: '#f0ece4',
              fontSize: 12,
            }}
            labelStyle={{ color: 'rgba(226,207,234,0.5)', fontSize: 11 }}
            itemStyle={{ color: '#c9a84c' }}
            formatter={(value: number) => [`\u20AC${value.toLocaleString('fr-FR')}`, 'Value']}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#c9a84c"
            strokeWidth={2}
            fill="url(#goldGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
