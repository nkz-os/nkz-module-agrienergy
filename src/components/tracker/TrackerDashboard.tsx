/**
 * TrackerDashboard — Main dashboard for a selected AgriEnergyTracker entity.
 * Shows gauges, orientation compass, power comparison, and sensor grid.
 */
import React from 'react';
import { Card } from '@nekazari/ui-kit';
import { useTranslation } from '@nekazari/sdk';
import { GaugeCard } from '../ui/GaugeCard';
import { StatusBadge } from '../ui/StatusBadge';
import {
  Gauge,
  Sun,
  Zap,
  Compass,
  Activity,
  ThermometerSun,
  Wind,
  Droplets,
  Leaf,
} from 'lucide-react';

interface TrackerStatus {
  tracker_id: string;
  orientation: { tilt: number; azimuth: number };
  power: { measured_w?: number; expected_w?: number };
  storage?: { soc?: number };
  sensors: Record<string, number>;
  signal_mapping?: { contextKey: string; entityId: string; attribute: string }[] | null;
  active_algorithm_id?: string | null;
  timestamp: string;
}

interface TrackerDashboardProps {
  status: TrackerStatus;
}

/** Determine tracker status from timestamp freshness */
function getTrackerHealth(timestamp: string): 'ok' | 'warning' | 'offline' {
  const age = Date.now() - new Date(timestamp).getTime();
  if (age < 60_000) return 'ok'; // < 1 min
  if (age < 300_000) return 'warning'; // < 5 min
  return 'offline';
}

/** Simple SVG compass showing panel azimuth direction */
const MiniCompass: React.FC<{ azimuth: number; tilt: number }> = ({ azimuth, tilt }) => {
  const needleAngle = azimuth - 90; // CSS rotation: 0=East, we want 0=North
  const tiltScale = Math.max(0.3, 1 - Math.abs(tilt) / 90);
  return (
    <svg width="64" height="64" viewBox="0 0 64 64" className="mx-auto">
      {/* Outer ring */}
      <circle cx="32" cy="32" r="28" fill="none" stroke="#d1d5db" strokeWidth="1.5" className="dark:stroke-gray-600" />
      {/* Cardinal marks */}
      <text x="32" y="8" textAnchor="middle" fontSize="7" className="fill-gray-400 dark:fill-gray-500" fontWeight="600">N</text>
      <text x="58" y="35" textAnchor="middle" fontSize="7" className="fill-gray-400 dark:fill-gray-500">E</text>
      <text x="32" y="60" textAnchor="middle" fontSize="7" className="fill-gray-400 dark:fill-gray-500">S</text>
      <text x="6" y="35" textAnchor="middle" fontSize="7" className="fill-gray-400 dark:fill-gray-500">W</text>
      {/* Panel direction needle */}
      <g transform={`rotate(${needleAngle}, 32, 32)`}>
        <line x1="32" y1="32" x2="32" y2={32 - 20 * tiltScale} stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" />
        <polygon points="32,10 28,18 36,18" fill="#3b82f6" opacity={tiltScale} />
      </g>
      {/* Center dot */}
      <circle cx="32" cy="32" r="2.5" fill="#3b82f6" />
    </svg>
  );
};

/** Icon mapping for known sensor context keys */
const SENSOR_ICONS: Record<string, React.ReactNode> = {
  'weather.ghi': React.createElement(Sun, { size: 12, className: 'text-amber-500' }),
  'weather.dni': React.createElement(Sun, { size: 12, className: 'text-orange-500' }),
  'weather.dhi': React.createElement(Sun, { size: 12, className: 'text-yellow-500' }),
  'weather.temperature': React.createElement(ThermometerSun, { size: 12, className: 'text-red-500' }),
  'weather.wind_speed': React.createElement(Wind, { size: 12, className: 'text-blue-500' }),
  'weather.humidity': React.createElement(Droplets, { size: 12, className: 'text-cyan-500' }),
  'crop.stress_index': React.createElement(Leaf, { size: 12, className: 'text-green-500' }),
  'crop.leaf_temperature': React.createElement(ThermometerSun, { size: 12, className: 'text-lime-500' }),
  'crop.par': React.createElement(Activity, { size: 12, className: 'text-purple-500' }),
};

/** Color thresholds for known sensor values */
function getSensorColor(key: string, value: number): string {
  if (key === 'weather.temperature') {
    if (value > 35) return 'text-red-600 dark:text-red-400';
    if (value < 2) return 'text-blue-600 dark:text-blue-400';
    return 'text-gray-900 dark:text-gray-100';
  }
  if (key === 'weather.wind_speed') {
    if (value > 15) return 'text-red-600 dark:text-red-400';
    if (value > 10) return 'text-amber-600 dark:text-amber-400';
    return 'text-gray-900 dark:text-gray-100';
  }
  if (key === 'crop.stress_index') {
    if (value > 0.8) return 'text-red-600 dark:text-red-400';
    if (value > 0.5) return 'text-amber-600 dark:text-amber-400';
    return 'text-gray-900 dark:text-gray-100';
  }
  return 'text-gray-900 dark:text-gray-100';
}

export const TrackerDashboard: React.FC<TrackerDashboardProps> = ({ status }) => {
  const { t } = useTranslation();
  const health = getTrackerHealth(status.timestamp);

  const healthLabel =
    health === 'ok'
      ? t('agrienergy.dashboard.statusOk')
      : health === 'warning'
        ? t('agrienergy.dashboard.statusWarning')
        : t('agrienergy.dashboard.statusOffline');

  const efficiency =
    status.power.measured_w != null && status.power.expected_w != null && status.power.expected_w > 0
      ? ((status.power.measured_w / status.power.expected_w) * 100).toFixed(0)
      : null;

  const ghi = status.sensors['weather.ghi'] ?? null;
  const maxPower = Math.max(status.power.expected_w ?? 0, status.power.measured_w ?? 0, 1000);

  const sensorEntries = Object.entries(status.sensors);

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <Zap size={16} className="text-emerald-500 flex-shrink-0" />
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
            {status.tracker_id}
          </span>
        </div>
        <StatusBadge status={health} label={healthLabel} />
      </div>

      {/* Gauge row */}
      <div className="grid grid-cols-3 gap-2">
        <GaugeCard
          label={t('agrienergy.dashboard.tilt')}
          value={status.orientation.tilt}
          min={-60}
          max={60}
          unit={t('agrienergy.panel.deg')}
          color="#3b82f6"
          icon={React.createElement(Gauge, { size: 12 })}
        />
        <GaugeCard
          label={t('agrienergy.dashboard.power')}
          value={status.power.measured_w ?? 0}
          max={maxPower}
          unit={t('agrienergy.panel.W')}
          color="#10b981"
          icon={React.createElement(Zap, { size: 12 })}
        />
        <GaugeCard
          label="GHI"
          value={ghi ?? 0}
          max={1200}
          unit="W/m\u00B2"
          color="#f59e0b"
          icon={React.createElement(Sun, { size: 12 })}
        />
      </div>

      {/* Orientation card */}
      <Card className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
        <div className="p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <Compass size={14} className="text-blue-500" />
            <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
              {t('agrienergy.dashboard.orientation')}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <MiniCompass azimuth={status.orientation.azimuth} tilt={status.orientation.tilt} />
            <div className="flex-1 space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">{t('agrienergy.panel.tilt')}</span>
                <span className="font-mono font-semibold text-gray-900 dark:text-gray-100">
                  {status.orientation.tilt.toFixed(1)}{t('agrienergy.panel.deg')}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">{t('agrienergy.panel.azimuth')}</span>
                <span className="font-mono font-semibold text-gray-900 dark:text-gray-100">
                  {status.orientation.azimuth.toFixed(1)}{t('agrienergy.panel.deg')}
                </span>
              </div>
              {status.storage?.soc != null && (
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500 dark:text-gray-400">{t('agrienergy.dashboard.battery')}</span>
                  <span className="font-mono font-semibold text-gray-900 dark:text-gray-100">
                    {status.storage.soc.toFixed(0)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Power card */}
      <Card className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
        <div className="p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <Zap size={14} className="text-emerald-500" />
            <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
              {t('agrienergy.dashboard.powerDetails')}
            </span>
          </div>
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-gray-500 dark:text-gray-400">{t('agrienergy.panel.measuredPower')}</span>
              <span className="font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                {status.power.measured_w != null ? `${status.power.measured_w.toFixed(0)} ${t('agrienergy.panel.W')}` : '\u2014'}
              </span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-gray-500 dark:text-gray-400">{t('agrienergy.panel.expectedPower')}</span>
              <span className="font-mono font-semibold text-blue-600 dark:text-blue-400">
                {status.power.expected_w != null ? `${status.power.expected_w.toFixed(0)} ${t('agrienergy.panel.W')}` : '\u2014'}
              </span>
            </div>
            {efficiency != null && (
              <div className="flex justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">{t('agrienergy.dashboard.efficiency')}</span>
                <span
                  className={
                    'font-mono font-bold ' +
                    (Number(efficiency) >= 90
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : Number(efficiency) >= 70
                        ? 'text-amber-600 dark:text-amber-400'
                        : 'text-red-600 dark:text-red-400')
                  }
                >
                  {efficiency}%
                </span>
              </div>
            )}
            {/* Power bar */}
            {status.power.measured_w != null && status.power.expected_w != null && (
              <div className="mt-1">
                <div className="h-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(100, status.power.expected_w > 0 ? (status.power.measured_w / status.power.expected_w) * 100 : 0)}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Sensors card */}
      {sensorEntries.length > 0 && (
        <Card className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
          <div className="p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <Activity size={14} className="text-purple-500" />
              <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
                {t('agrienergy.panel.sensors')}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
              {sensorEntries.map(([key, value]) => {
                const sensorLabel = t(`agrienergy.sensorLabels.${key}` as any) || key;
                const icon = SENSOR_ICONS[key] || React.createElement(Activity, { size: 12, className: 'text-gray-400' });
                const colorClass = getSensorColor(key, value);
                const displayVal = value != null && Number.isFinite(value) ? value.toFixed(1) : '\u2014';

                return (
                  <div key={key} className="flex items-center gap-1.5 text-xs">
                    {icon}
                    <span className="text-gray-500 dark:text-gray-400 truncate flex-1">{sensorLabel}</span>
                    <span className={'font-mono font-semibold ' + colorClass}>{displayVal}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      )}

      {sensorEntries.length === 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic px-1">
          {t('agrienergy.signals.configureHint')}
        </p>
      )}

      {/* Last update */}
      <p className="text-[10px] text-gray-400 dark:text-gray-500 text-right px-1">
        {t('agrienergy.panel.lastUpdate')}: {status.timestamp ? new Date(status.timestamp).toLocaleTimeString() : '\u2014'}
      </p>
    </div>
  );
};
