/**
 * AgriEnergySandbox — Main context-panel component for the AgriEnergy module.
 *
 * - No entity selected: shows ParkOverview
 * - AgriEnergyTracker selected: shows TrackerDashboard + collapsible sections
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, Button } from '@nekazari/ui-kit';
import { SlotShell } from '@nekazari/viewer-kit';
import { useTranslation, useViewerOptional } from '@nekazari/sdk';
import { ChevronDown, ChevronRight, Zap, FlaskConical } from 'lucide-react';
import { ParkOverview } from '../park/ParkOverview';
import { TrackerDashboard } from '../tracker/TrackerDashboard';
import { ManualControls } from '../tracker/ManualControls';
import { AlgorithmPanel } from '../tracker/AlgorithmPanel';
import { ConfigureSignals } from './ConfigureSignals';

const agrienergyAccent = { base: '#F97316', soft: '#FFF7ED', strong: '#C2410C' };

const STATUS_POLL_INTERVAL_MS = 10_000;

function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
}

interface SignalMappingRow {
  contextKey: string;
  entityId: string;
  attribute: string;
}

interface TrackerStatus {
  tracker_id: string;
  orientation: { tilt: number; azimuth: number };
  power: { measured_w?: number; expected_w?: number };
  storage?: { soc?: number };
  sensors: Record<string, number>;
  signal_mapping?: SignalMappingRow[] | null;
  active_algorithm_id?: string | null;
  timestamp: string;
}

/** Collapsible section wrapper */
const CollapsibleSection: React.FC<{
  title: string;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}> = ({ title, icon, defaultOpen = false, children }) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Card className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
      >
        <span className="text-gray-500 dark:text-gray-400 transition-transform duration-200">
          {open
            ? React.createElement(ChevronDown, { size: 14 })
            : React.createElement(ChevronRight, { size: 14 })}
        </span>
        {icon && <span className="flex-shrink-0">{icon}</span>}
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 flex-1 text-left">
          {title}
        </span>
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </Card>
  );
};

export const AgriEnergySandbox: React.FC = () => {
  const { t } = useTranslation();
  const viewer = useViewerOptional();
  const selectedEntityId = viewer?.selectedEntityId ?? null;

  const [status, setStatus] = useState<TrackerStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Sandbox simulation state
  const [targetTilt, setTargetTilt] = useState<number>(30);
  const [simLoading, setSimLoading] = useState(false);
  const [simResult, setSimResult] = useState<any>(null);

  const fetchStatus = useCallback(async () => {
    if (!selectedEntityId) {
      setStatus(null);
      setStatusError(null);
      return;
    }
    try {
      const res = await fetchWithAuth(
        `/api/agrienergy/status?tracker_id=${encodeURIComponent(selectedEntityId)}`
      );
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        setStatusError(null);
      } else {
        setStatus(null);
        setStatusError('Not found');
      }
    } catch {
      setStatus(null);
      setStatusError(t('agrienergy.panel.noData'));
    }
  }, [selectedEntityId, t]);

  useEffect(() => {
    fetchStatus();
    if (!selectedEntityId) return;
    const id = setInterval(fetchStatus, STATUS_POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [selectedEntityId, fetchStatus]);

  // Reset simulation when entity changes
  useEffect(() => {
    setSimResult(null);
  }, [selectedEntityId]);

  const runSimulation = async () => {
    setSimLoading(true);
    try {
      const res = await fetchWithAuth('/api/agrienergy/simulate', {
        method: 'POST',
        body: JSON.stringify({
          tracker: {
            id: selectedEntityId || 'tracker-01',
            panel_width: 2.0,
            panel_length: 4.0,
            capacity_w: 1000,
            min_tilt: -60,
            max_tilt: 60,
            lat: 43.3,
            lon: -2.0,
            parent_parcel_id: 'parcel-01',
          },
          parcel: { id: 'parcel-01', slope: 5.0, aspect: 180.0 },
          telemetry: {
            timestamp: new Date().toISOString(),
            ghi: status?.sensors['weather.ghi'] ?? 800,
            dni: status?.sensors['weather.dni'] ?? 600,
            dhi: status?.sensors['weather.dhi'] ?? 200,
            actual_tilt: status?.orientation.tilt ?? 0,
            actual_azimuth: status?.orientation.azimuth ?? 180,
          },
          target_tilt: targetTilt,
        }),
      });
      const data = await res.json();
      setSimResult(data);
    } catch {
      // Silently fail — no console.log in production
    } finally {
      setSimLoading(false);
    }
  };

  // No entity selected — show park overview
  if (!selectedEntityId) {
    return (
      <SlotShell moduleId="agrienergy" accent={agrienergyAccent}>
        <ParkOverview />
      </SlotShell>
    );
  }

  // Entity selected but no data yet
  if (!status && !statusError) {
    return (
      <SlotShell moduleId="agrienergy" accent={agrienergyAccent}>
        <div className="p-4 text-center">
          <div className="animate-pulse flex flex-col items-center gap-2">
            <Zap size={20} className="text-gray-300 dark:text-gray-600" />
            <p className="text-xs text-gray-500 dark:text-gray-400">{t('common.loading')}</p>
          </div>
        </div>
      </SlotShell>
    );
  }

  // Entity selected but error / not found
  if (!status && statusError) {
    return (
      <SlotShell moduleId="agrienergy" accent={agrienergyAccent}>
        <div className="p-4 text-center">
          <Zap size={20} className="text-amber-400 mx-auto mb-2" />
          <p className="text-xs text-amber-600 dark:text-amber-400">{t('agrienergy.panel.noData')}</p>
          <p className="text-[10px] text-gray-400 mt-1">{selectedEntityId}</p>
        </div>
        <ParkOverview />
      </SlotShell>
    );
  }

  // Entity selected with data
  return (
    <SlotShell moduleId="agrienergy" accent={agrienergyAccent}>
      {/* 1. TrackerDashboard (always expanded) */}
      {status && <TrackerDashboard status={status} />}

      {/* 2. Manual Controls (collapsible) */}
      {status && (
        <CollapsibleSection
          title={t('agrienergy.manual.title')}
          icon={React.createElement(Zap, { size: 14, className: 'text-amber-500' })}
        >
          <ManualControls
            trackerId={selectedEntityId}
            currentTilt={status.orientation.tilt}
            currentAzimuth={status.orientation.azimuth}
            onApplied={fetchStatus}
          />
        </CollapsibleSection>
      )}

      {/* 3. Algorithm Panel (collapsible) */}
      <CollapsibleSection
        title={t('agrienergy.algorithms.title')}
        icon={React.createElement(FlaskConical, { size: 14, className: 'text-blue-500' })}
      >
        <AlgorithmPanel
          trackerId={selectedEntityId}
          currentAlgorithmId={status?.active_algorithm_id}
          onSaved={fetchStatus}
        />
      </CollapsibleSection>

      {/* 4. Configure Signals (collapsible) */}
      <CollapsibleSection
        title={t('agrienergy.signals.title')}
        icon={React.createElement(Zap, { size: 14, className: 'text-purple-500' })}
      >
        <ConfigureSignals
          trackerId={selectedEntityId}
          currentMapping={status?.signal_mapping}
          onSaved={fetchStatus}
        />
      </CollapsibleSection>

      {/* 5. Sandbox simulation (collapsible) */}
      <CollapsibleSection
        title={t('agrienergy.sandbox.title')}
        icon={React.createElement(FlaskConical, { size: 14, className: 'text-emerald-500' })}
      >
        <div className="space-y-3">
          <div>
            <div className="flex justify-between text-[10px] text-gray-500 dark:text-gray-400 mb-0.5">
              <span>{t('agrienergy.sandbox.targetTiltLabel')}</span>
              <span className="font-mono font-semibold text-blue-600 dark:text-blue-400">
                {targetTilt}{t('agrienergy.panel.deg')}
              </span>
            </div>
            <input
              type="range"
              min={-60}
              max={60}
              value={targetTilt}
              onChange={(e) => setTargetTilt(Number(e.target.value))}
              className="w-full h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full appearance-none cursor-pointer accent-blue-500"
            />
            <div className="flex justify-between text-[9px] text-gray-400">
              <span>-60{t('agrienergy.panel.deg')}</span>
              <span>0{t('agrienergy.panel.deg')}</span>
              <span>60{t('agrienergy.panel.deg')}</span>
            </div>
          </div>

          <Button
            onClick={runSimulation}
            disabled={simLoading}
            size="sm"
            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white text-xs"
          >
            {simLoading ? t('agrienergy.sandbox.simulating') : t('agrienergy.sandbox.runSimulation')}
          </Button>

          {simResult && (
            <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-3">
              <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                {t('agrienergy.sandbox.resultsTitle')}
              </h4>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-gray-500 dark:text-gray-400 block text-[10px]">
                    {t('agrienergy.sandbox.expectedPowerLabel')}
                  </span>
                  <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                    {simResult.expected_power_w?.toFixed(1) || 0} {t('agrienergy.panel.W')}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500 dark:text-gray-400 block text-[10px]">
                    {t('agrienergy.sandbox.shadowAreaLabel')}
                  </span>
                  <span className="font-mono font-bold text-purple-600 dark:text-purple-400">
                    {simResult.shadow_area_m2?.toFixed(2) || 0} m{'\u00B2'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </CollapsibleSection>
    </SlotShell>
  );
};
