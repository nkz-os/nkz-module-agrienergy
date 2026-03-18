/**
 * ConfigureSignals — Map algorithm context keys to platform entities/attributes.
 * Polished version with better grid layout, entity type icons, colored last values, clear buttons.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@nekazari/ui-kit';
import { useTranslation } from '@nekazari/sdk';
import {
  Sun,
  ThermometerSun,
  Wind,
  Droplets,
  Leaf,
  Activity,
  X,
} from 'lucide-react';

function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
}

const DEFAULT_CONTEXT_KEYS = [
  'weather.ghi',
  'weather.dni',
  'weather.dhi',
  'weather.temperature',
  'weather.wind_speed',
  'weather.humidity',
  'crop.stress_index',
  'crop.leaf_temperature',
  'crop.par',
];

interface SignalSourceAttribute {
  name: string;
  last_value?: number;
}

interface SignalSource {
  entity_id: string;
  entity_name: string;
  type: string;
  attributes: SignalSourceAttribute[];
}

interface MappingRow {
  contextKey: string;
  entityId: string;
  attribute: string;
}

interface ConfigureSignalsProps {
  trackerId: string | null;
  currentMapping: MappingRow[] | null | undefined;
  onSaved?: () => void;
}

/** Icon for context keys */
const CONTEXT_KEY_ICONS: Record<string, React.ReactNode> = {
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

/** Color for last value display */
function getLastValueColor(value: number | undefined): string {
  if (value == null) return 'text-gray-400';
  if (value === 0) return 'text-gray-500 dark:text-gray-400';
  return 'text-emerald-600 dark:text-emerald-400';
}

export const ConfigureSignals: React.FC<ConfigureSignalsProps> = ({
  trackerId,
  currentMapping,
  onSaved,
}) => {
  const { t } = useTranslation();
  const [sources, setSources] = useState<SignalSource[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [rows, setRows] = useState<MappingRow[]>(() =>
    DEFAULT_CONTEXT_KEYS.map((contextKey) => ({
      contextKey,
      entityId: '',
      attribute: 'value',
    }))
  );
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'ok' | 'error'>('idle');

  const fetchSources = useCallback(async () => {
    setLoadingSources(true);
    try {
      const res = await fetchWithAuth('/api/agrienergy/signal-sources');
      if (res.ok) {
        const data = await res.json();
        setSources(data.sources || []);
      }
    } catch {
      setSources([]);
    } finally {
      setLoadingSources(false);
    }
  }, []);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  useEffect(() => {
    if (currentMapping && currentMapping.length > 0) {
      const byKey: Record<string, MappingRow> = {};
      currentMapping.forEach((m) => {
        byKey[m.contextKey] = m;
      });
      setRows((prev) => prev.map((r) => byKey[r.contextKey] || r));
    }
  }, [currentMapping]);

  const setRow = (contextKey: string, field: 'entityId' | 'attribute', value: string) => {
    setRows((prev) =>
      prev.map((r) => (r.contextKey === contextKey ? { ...r, [field]: value } : r))
    );
    setSaveStatus('idle');
  };

  const clearRow = (contextKey: string) => {
    setRows((prev) =>
      prev.map((r) =>
        r.contextKey === contextKey ? { ...r, entityId: '', attribute: 'value' } : r
      )
    );
    setSaveStatus('idle');
  };

  const handleSave = async () => {
    if (!trackerId) return;
    const payload = rows
      .filter((r) => r.entityId && r.attribute)
      .map((r) => ({
        contextKey: r.contextKey,
        entityId: r.entityId,
        attribute: r.attribute,
      }));
    setSaving(true);
    setSaveStatus('idle');
    try {
      const res = await fetchWithAuth(
        `/api/agrienergy/trackers/${encodeURIComponent(trackerId)}/signal-mapping`,
        {
          method: 'PATCH',
          body: JSON.stringify({ signalMapping: payload }),
        }
      );
      if (res.ok) {
        setSaveStatus('ok');
        onSaved?.();
      } else {
        setSaveStatus('error');
      }
    } catch {
      setSaveStatus('error');
    } finally {
      setSaving(false);
    }
  };

  const getLabel = (key: string) => t(`agrienergy.sensorLabels.${key}` as any) || key;

  // Only show rows for keys that are relevant (have at least basic keys)
  const activeRows = rows.filter(
    (r) => DEFAULT_CONTEXT_KEYS.includes(r.contextKey)
  );
  const mappedCount = activeRows.filter((r) => r.entityId).length;

  if (!trackerId) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {t('agrienergy.signals.description')}
        </p>
        <span className="text-[10px] font-mono text-gray-400">
          {mappedCount}/{activeRows.length}
        </span>
      </div>

      {loadingSources && (
        <p className="text-xs text-gray-400">{t('common.loading')}</p>
      )}
      {!loadingSources && sources.length === 0 && (
        <p className="text-xs text-amber-600 dark:text-amber-400">{t('agrienergy.signals.noSources')}</p>
      )}

      {sources.length > 0 && (
        <>
          <div className="space-y-2">
            {activeRows.map((row) => {
              const selectedSource = sources.find((s) => s.entity_id === row.entityId);
              const selectedAttr = selectedSource?.attributes.find(
                (a) => a.name === row.attribute
              );
              const icon = CONTEXT_KEY_ICONS[row.contextKey] || React.createElement(Activity, { size: 12, className: 'text-gray-400' });

              return (
                <div
                  key={row.contextKey}
                  className="p-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 space-y-1.5"
                >
                  {/* Row header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {icon}
                      <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                        {getLabel(row.contextKey)}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {selectedAttr?.last_value != null && (
                        <span
                          className={
                            'text-[10px] font-mono font-semibold ' +
                            getLastValueColor(selectedAttr.last_value)
                          }
                        >
                          {selectedAttr.last_value}
                        </span>
                      )}
                      {row.entityId && (
                        <button
                          type="button"
                          onClick={() => clearRow(row.contextKey)}
                          className="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                          title={t('agrienergy.signals.clear')}
                        >
                          <X size={10} className="text-gray-400 hover:text-red-500" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Entity selector */}
                  <select
                    className="w-full rounded border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-2 py-1 text-[11px] text-gray-900 dark:text-gray-100"
                    value={row.entityId}
                    onChange={(e) => setRow(row.contextKey, 'entityId', e.target.value)}
                  >
                    <option value="">{t('agrienergy.signals.selectEntity')}</option>
                    {sources.map((s) => (
                      <option key={s.entity_id} value={s.entity_id}>
                        {s.entity_name} ({s.type})
                      </option>
                    ))}
                  </select>

                  {/* Attribute selector — only show if entity selected */}
                  {row.entityId && (
                    <select
                      className="w-full rounded border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-2 py-1 text-[11px] text-gray-900 dark:text-gray-100"
                      value={row.attribute}
                      onChange={(e) => setRow(row.contextKey, 'attribute', e.target.value)}
                    >
                      <option value="">{t('agrienergy.signals.selectAttribute')}</option>
                      {selectedSource?.attributes.map((a) => (
                        <option key={a.name} value={a.name}>
                          {a.name}
                          {a.last_value != null ? ` (${a.last_value})` : ''}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              );
            })}
          </div>

          <Button
            onClick={handleSave}
            disabled={saving}
            size="sm"
            className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs"
          >
            {saving ? t('common.loading') : t('agrienergy.signals.save')}
          </Button>

          {saveStatus === 'ok' && (
            <p className="text-xs text-emerald-600 dark:text-emerald-400">
              {t('agrienergy.signals.saved')}
            </p>
          )}
          {saveStatus === 'error' && (
            <p className="text-xs text-red-600 dark:text-red-400">
              {t('agrienergy.signals.error')}
            </p>
          )}
        </>
      )}
    </div>
  );
};
