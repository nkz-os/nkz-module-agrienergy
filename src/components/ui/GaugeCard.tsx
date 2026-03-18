/**
 * GaugeCard — Reusable radial semi-circular gauge with SVG.
 * Compact card designed for sidebar (320-400px) context panels.
 */
import React from 'react';

interface GaugeCardProps {
  label: string;
  value: number;
  max: number;
  unit: string;
  color?: string;
  icon?: React.ReactNode;
  /** Optional minimum value (for bipolar gauges like tilt -60..60) */
  min?: number;
}

const GAUGE_RADIUS = 36;
const GAUGE_STROKE = 6;
const GAUGE_CX = 44;
const GAUGE_CY = 44;
const ARC_START_ANGLE = Math.PI;
const ARC_END_ANGLE = 0;

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  return {
    x: cx + r * Math.cos(angle),
    y: cy - r * Math.sin(angle),
  };
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, startAngle);
  const end = polarToCartesian(cx, cy, r, endAngle);
  const largeArc = startAngle - endAngle > Math.PI ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}

export const GaugeCard: React.FC<GaugeCardProps> = ({
  label,
  value,
  max,
  unit,
  color = '#10b981',
  icon,
  min = 0,
}) => {
  const range = max - min;
  const clampedValue = Math.max(min, Math.min(max, value));
  const fraction = range > 0 ? (clampedValue - min) / range : 0;

  // Arc goes from PI (left) to 0 (right) — semicircle
  const fillAngle = ARC_START_ANGLE - fraction * (ARC_START_ANGLE - ARC_END_ANGLE);

  const bgPath = describeArc(GAUGE_CX, GAUGE_CY, GAUGE_RADIUS, ARC_START_ANGLE, ARC_END_ANGLE);
  const fillPath = describeArc(GAUGE_CX, GAUGE_CY, GAUGE_RADIUS, ARC_START_ANGLE, fillAngle);

  const displayValue = Number.isFinite(value) ? value : 0;
  const formattedValue =
    Math.abs(displayValue) >= 1000
      ? displayValue.toFixed(0)
      : Math.abs(displayValue) >= 100
        ? displayValue.toFixed(0)
        : displayValue.toFixed(1);

  return (
    <div className="flex flex-col items-center p-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 min-w-0">
      <svg width="88" height="52" viewBox="0 0 88 52" className="overflow-visible">
        {/* Background arc */}
        <path
          d={bgPath}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={GAUGE_STROKE}
          strokeLinecap="round"
          className="dark:stroke-gray-600"
        />
        {/* Filled arc with transition */}
        <path
          d={fillPath}
          fill="none"
          stroke={color}
          strokeWidth={GAUGE_STROKE}
          strokeLinecap="round"
          style={{
            transition: 'stroke-dashoffset 0.6s ease-out',
          }}
        />
      </svg>
      <div className="flex items-center gap-1 -mt-1">
        {icon && <span className="text-gray-500 dark:text-gray-400">{icon}</span>}
        <span className="font-mono text-sm font-bold text-gray-900 dark:text-gray-100">
          {formattedValue}
        </span>
        <span className="text-[10px] text-gray-500 dark:text-gray-400">{unit}</span>
      </div>
      <span className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5 text-center leading-tight truncate max-w-full">
        {label}
      </span>
    </div>
  );
};
