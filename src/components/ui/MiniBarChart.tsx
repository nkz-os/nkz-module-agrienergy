/**
 * MiniBarChart — Pure SVG horizontal bar chart for compact sidebar display.
 */
import React from 'react';

interface BarDatum {
  label: string;
  value: number;
}

interface MiniBarChartProps {
  data: BarDatum[];
  max?: number;
  height?: number;
  barColor?: string;
}

const BAR_HEIGHT = 14;
const BAR_GAP = 4;
const LABEL_WIDTH = 60;
const VALUE_WIDTH = 40;
const BAR_AREA_START = LABEL_WIDTH + 4;

export const MiniBarChart: React.FC<MiniBarChartProps> = ({
  data,
  max: maxProp,
  height: heightProp,
  barColor = '#10b981',
}) => {
  const maxValue = maxProp ?? Math.max(...data.map((d) => d.value), 1);
  const totalHeight = heightProp ?? data.length * (BAR_HEIGHT + BAR_GAP) + BAR_GAP;
  const chartWidth = 280;
  const barMaxWidth = chartWidth - BAR_AREA_START - VALUE_WIDTH - 8;

  return (
    <svg
      width="100%"
      height={totalHeight}
      viewBox={`0 0 ${chartWidth} ${totalHeight}`}
      className="overflow-visible"
    >
      {data.map((d, i) => {
        const y = BAR_GAP + i * (BAR_HEIGHT + BAR_GAP);
        const barWidth = maxValue > 0 ? (d.value / maxValue) * barMaxWidth : 0;
        const displayVal =
          Math.abs(d.value) >= 1000
            ? (d.value / 1000).toFixed(1) + 'k'
            : d.value % 1 === 0
              ? String(d.value)
              : d.value.toFixed(1);

        return (
          <g key={d.label + '-' + i}>
            {/* Label */}
            <text
              x={LABEL_WIDTH}
              y={y + BAR_HEIGHT / 2 + 1}
              textAnchor="end"
              className="fill-gray-600 dark:fill-gray-400"
              fontSize="9"
              fontFamily="monospace"
            >
              {d.label}
            </text>
            {/* Background bar */}
            <rect
              x={BAR_AREA_START}
              y={y}
              width={barMaxWidth}
              height={BAR_HEIGHT}
              rx={3}
              className="fill-gray-100 dark:fill-gray-700"
            />
            {/* Value bar */}
            <rect
              x={BAR_AREA_START}
              y={y}
              width={Math.max(0, barWidth)}
              height={BAR_HEIGHT}
              rx={3}
              fill={barColor}
              opacity={0.85}
              style={{ transition: 'width 0.4s ease-out' }}
            />
            {/* Value text */}
            <text
              x={BAR_AREA_START + barMaxWidth + 6}
              y={y + BAR_HEIGHT / 2 + 1}
              textAnchor="start"
              className="fill-gray-700 dark:fill-gray-300"
              fontSize="9"
              fontWeight="600"
              fontFamily="monospace"
            >
              {displayVal}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
