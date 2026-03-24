import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface Segment {
  label: string;
  value: number;
  color: string;
}

interface AllocationDonutProps {
  segments: Segment[];
  total: string;
}

export function AllocationDonut({ segments, total }: AllocationDonutProps) {
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={segments}
            dataKey="value"
            nameKey="label"
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={85}
            strokeWidth={0}
          >
            {segments.map((segment, index) => (
              <Cell key={`cell-${index}`} fill={segment.color} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>

      {/* Center label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-xl font-bold text-mm-gold">{total}</span>
        <span className="text-[11px] text-mm-text-muted">Total Value</span>
      </div>
    </div>
  );
}
