/**
 * AlgorithmPanel — Visual card-based algorithm selector.
 * Shows each preset as a card with icon, description, and trigger condition.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@nekazari/ui-kit';
import { useTranslation } from '@nekazari/sdk';
import {
  Sun,
  Shield,
  ThermometerSun,
  Wind,
  Snowflake,
  Droplets,
  Leaf,
  Settings,
  Check,
} from 'lucide-react';

function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
}

interface AlgorithmPreset {
  id: string;
  name: string;
  logic: Record<string, unknown>;
}

interface AlgorithmPanelProps {
  trackerId: string;
  currentAlgorithmId?: string | null;
  onSaved?: () => void;
}

/** Known algorithm preset metadata */
interface PresetMeta {
  icon: React.ReactNode;
  descriptionKey: string;
  triggerKey: string;
  accentColor: string;
  borderColor: string;
}

const PRESET_META: Record<string, PresetMeta> = {
  'default:maximize': {
    icon: React.createElement(Sun, { size: 18 }),
    descriptionKey: 'agrienergy.algorithmDescriptions.maximize',
    triggerKey: 'agrienergy.algorithmTriggers.maximize',
    accentColor: 'text-amber-500',
    borderColor: 'border-amber-300 dark:border-amber-600',
  },
  'default:hierarchical_failsafe': {
    icon: React.createElement(Shield, { size: 18 }),
    descriptionKey: 'agrienergy.algorithmDescriptions.hierarchical_failsafe',
    triggerKey: 'agrienergy.algorithmTriggers.hierarchical_failsafe',
    accentColor: 'text-blue-500',
    borderColor: 'border-blue-300 dark:border-blue-600',
  },
  thermal_stress: {
    icon: React.createElement(ThermometerSun, { size: 18 }),
    descriptionKey: 'agrienergy.algorithmDescriptions.thermal_stress',
    triggerKey: 'agrienergy.algorithmTriggers.thermal_stress',
    accentColor: 'text-red-500',
    borderColor: 'border-red-300 dark:border-red-600',
  },
  wind_barrier: {
    icon: React.createElement(Wind, { size: 18 }),
    descriptionKey: 'agrienergy.algorithmDescriptions.wind_barrier',
    triggerKey: 'agrienergy.algorithmTriggers.wind_barrier',
    accentColor: 'text-sky-500',
    borderColor: 'border-sky-300 dark:border-sky-600',
  },
  frost_prevention: {
    icon: React.createElement(Snowflake, { size: 18 }),
    descriptionKey: 'agrienergy.algorithmDescriptions.frost_prevention',
    triggerKey: 'agrienergy.algorithmTriggers.frost_prevention',
    accentColor: 'text-cyan-500',
    borderColor: 'border-cyan-300 dark:border-cyan-600',
  },
  hydric_stress: {
    icon: React.createElement(Droplets, { size: 18 }),
    descriptionKey: 'agrienergy.algorithmDescriptions.hydric_stress',
    triggerKey: 'agrienergy.algorithmTriggers.hydric_stress',
    accentColor: 'text-teal-500',
    borderColor: 'border-teal-300 dark:border-teal-600',
  },
  par_optimization: {
    icon: React.createElement(Leaf, { size: 18 }),
    descriptionKey: 'agrienergy.algorithmDescriptions.par_optimization',
    triggerKey: 'agrienergy.algorithmTriggers.par_optimization',
    accentColor: 'text-green-500',
    borderColor: 'border-green-300 dark:border-green-600',
  },
};

export const AlgorithmPanel: React.FC<AlgorithmPanelProps> = ({
  trackerId,
  currentAlgorithmId,
  onSaved,
}) => {
  const { t } = useTranslation();
  const [algorithms, setAlgorithms] = useState<AlgorithmPreset[]>([]);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<'ok' | 'error' | null>(null);

  const fetchAlgorithms = useCallback(async () => {
    try {
      const res = await fetchWithAuth('/api/agrienergy/algorithms');
      if (res.ok) {
        const data = await res.json();
        setAlgorithms(data.algorithms || []);
      }
    } catch {
      setAlgorithms([]);
    }
  }, []);

  useEffect(() => {
    fetchAlgorithms();
  }, [fetchAlgorithms]);

  const handleSelect = (algorithmId: string) => {
    if (algorithmId === currentAlgorithmId) return;
    setPendingId(algorithmId);
    setFeedback(null);
  };

  const handleConfirm = async () => {
    if (!pendingId) return;
    setSaving(true);
    setFeedback(null);
    try {
      const res = await fetchWithAuth(
        `/api/agrienergy/trackers/${encodeURIComponent(trackerId)}/algorithm`,
        {
          method: 'PATCH',
          body: JSON.stringify({ activeAlgorithm: { id: pendingId } }),
        }
      );
      if (res.ok) {
        setFeedback('ok');
        setPendingId(null);
        onSaved?.();
      } else {
        setFeedback('error');
      }
    } catch {
      setFeedback('error');
    } finally {
      setSaving(false);
    }
  };

  const isCurrentCustom =
    currentAlgorithmId != null &&
    algorithms.length > 0 &&
    !algorithms.some((a) => a.id === currentAlgorithmId);

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {t('agrienergy.algorithms.description')}
      </p>

      <div className="space-y-1.5">
        {algorithms.map((algo) => {
          const meta = PRESET_META[algo.id];
          const isActive = algo.id === currentAlgorithmId;
          const isPending = algo.id === pendingId;

          return (
            <button
              key={algo.id}
              type="button"
              onClick={() => handleSelect(algo.id)}
              disabled={saving}
              className={
                'w-full text-left p-2.5 rounded-lg border transition-all duration-200 ' +
                (isActive
                  ? (meta?.borderColor || 'border-emerald-400 dark:border-emerald-600') +
                    ' bg-white dark:bg-gray-800 ring-1 ring-emerald-400/50 dark:ring-emerald-600/50'
                  : isPending
                    ? 'border-blue-300 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-750')
              }
            >
              <div className="flex items-start gap-2">
                <span className={'flex-shrink-0 mt-0.5 ' + (meta?.accentColor || 'text-gray-500')}>
                  {meta?.icon || React.createElement(Settings, { size: 18 })}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-semibold text-gray-900 dark:text-gray-100 truncate">
                      {algo.name}
                    </span>
                    {isActive && (
                      <span className="flex-shrink-0">
                        <Check size={12} className="text-emerald-500" />
                      </span>
                    )}
                  </div>
                  {meta && (
                    <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5 leading-snug">
                      {t(meta.descriptionKey)}
                    </p>
                  )}
                  {meta && (
                    <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 font-mono">
                      {t(meta.triggerKey)}
                    </p>
                  )}
                </div>
              </div>
            </button>
          );
        })}

        {/* Custom indicator */}
        {isCurrentCustom && (
          <div className="p-2.5 rounded-lg border border-purple-300 dark:border-purple-600 bg-purple-50 dark:bg-purple-900/20 ring-1 ring-purple-400/50">
            <div className="flex items-center gap-2">
              <Settings size={18} className="text-purple-500" />
              <div>
                <span className="text-xs font-semibold text-gray-900 dark:text-gray-100">
                  {t('agrienergy.algorithms.customActive')}
                </span>
                <p className="text-[10px] text-gray-500 dark:text-gray-400">
                  {t('agrienergy.algorithms.customDescription')}
                </p>
              </div>
              <Check size={12} className="text-purple-500 ml-auto flex-shrink-0" />
            </div>
          </div>
        )}
      </div>

      {/* Confirmation */}
      {pendingId && (
        <div className="flex gap-2 pt-1">
          <Button
            size="sm"
            onClick={handleConfirm}
            disabled={saving}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-xs"
          >
            {saving ? t('common.loading') : t('agrienergy.algorithms.activate')}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setPendingId(null)}
            disabled={saving}
            className="text-xs"
          >
            {t('agrienergy.parks.cancel')}
          </Button>
        </div>
      )}

      {feedback === 'ok' && (
        <p className="text-xs text-emerald-600 dark:text-emerald-400">{t('agrienergy.algorithms.saved')}</p>
      )}
      {feedback === 'error' && (
        <p className="text-xs text-red-600 dark:text-red-400">{t('agrienergy.algorithms.error')}</p>
      )}
    </div>
  );
};
