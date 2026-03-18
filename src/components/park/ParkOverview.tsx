/**
 * ParkOverview — Park management and tracker overview table.
 * Shown when no entity is selected. Includes park selector, summary, tracker table, and create form.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, Button } from '@nekazari/ui-kit';
import { useTranslation, useViewerOptional } from '@nekazari/sdk';
import { StatusBadge } from '../ui/StatusBadge';
import {
  Building2,
  Plus,
  Zap,
  LayoutGrid,
  RefreshCw,
} from 'lucide-react';

function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
}

interface ParkSummary {
  park_id: string;
  name: string;
  ref_agri_parcel: string;
  parcel_name?: string;
  tracker_count: number;
  tracker_ids: string[];
}

interface TrackerRow {
  tracker_id: string;
  name?: string;
  tilt?: number;
  azimuth?: number;
  power_w?: number;
  status?: 'ok' | 'warning' | 'critical' | 'offline';
  algorithm_name?: string;
}

interface ParcelItem {
  id: string;
  name: string;
}

interface TrackerStatusResponse {
  tracker_id: string;
  orientation: { tilt: number; azimuth: number };
  power: { measured_w?: number; expected_w?: number };
  active_algorithm_id?: string | null;
  timestamp: string;
}

export const ParkOverview: React.FC = () => {
  const { t } = useTranslation();
  const viewer = useViewerOptional();

  const [parks, setParks] = useState<ParkSummary[]>([]);
  const [parcels, setParcels] = useState<ParcelItem[]>([]);
  const [selectedParkId, setSelectedParkId] = useState<string | null>(null);
  const [trackerRows, setTrackerRows] = useState<TrackerRow[]>([]);
  const [loadingParks, setLoadingParks] = useState(false);
  const [loadingTrackers, setLoadingTrackers] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Create form
  const [createName, setCreateName] = useState('');
  const [createParcelId, setCreateParcelId] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const fetchParks = useCallback(async () => {
    setLoadingParks(true);
    try {
      const res = await fetchWithAuth('/api/agrienergy/parks');
      if (res.ok) {
        const data = await res.json();
        setParks(data.parks || []);
      }
    } catch {
      setParks([]);
    } finally {
      setLoadingParks(false);
    }
  }, []);

  const fetchParcels = useCallback(async () => {
    try {
      const res = await fetchWithAuth('/api/agrienergy/parcels');
      if (res.ok) {
        const data = await res.json();
        setParcels(data.parcels || []);
      }
    } catch {
      setParcels([]);
    }
  }, []);

  useEffect(() => {
    fetchParks();
    fetchParcels();
  }, [fetchParks, fetchParcels]);

  // Load tracker details when a park is selected
  useEffect(() => {
    if (!selectedParkId) {
      setTrackerRows([]);
      return;
    }
    setLoadingTrackers(true);

    fetchWithAuth(`/api/agrienergy/parks/${encodeURIComponent(selectedParkId)}/trackers`)
      .then((res) => (res.ok ? res.json() : { trackers: [] }))
      .then(async (data: { trackers?: { tracker_id: string; name?: string }[] }) => {
        const trackers = data.trackers || [];
        // Fetch individual tracker statuses in parallel
        const rows: TrackerRow[] = await Promise.all(
          trackers.map(async (tr) => {
            const row: TrackerRow = { tracker_id: tr.tracker_id, name: tr.name };
            try {
              const sRes = await fetchWithAuth(
                `/api/agrienergy/status?tracker_id=${encodeURIComponent(tr.tracker_id)}`
              );
              if (sRes.ok) {
                const s: TrackerStatusResponse = await sRes.json();
                row.tilt = s.orientation.tilt;
                row.azimuth = s.orientation.azimuth;
                row.power_w = s.power.measured_w ?? s.power.expected_w;
                row.algorithm_name = s.active_algorithm_id ?? undefined;
                const age = Date.now() - new Date(s.timestamp).getTime();
                row.status = age < 60_000 ? 'ok' : age < 300_000 ? 'warning' : 'offline';
              } else {
                row.status = 'offline';
              }
            } catch {
              row.status = 'offline';
            }
            return row;
          })
        );
        setTrackerRows(rows);
      })
      .catch(() => setTrackerRows([]))
      .finally(() => setLoadingTrackers(false));
  }, [selectedParkId]);

  const handleCreatePark = async () => {
    if (!createName.trim() || !createParcelId.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const res = await fetchWithAuth('/api/agrienergy/parks', {
        method: 'POST',
        body: JSON.stringify({ name: createName.trim(), ref_agri_parcel: createParcelId }),
      });
      if (res.ok) {
        setShowCreateForm(false);
        setCreateName('');
        setCreateParcelId('');
        fetchParks();
      } else {
        const d = await res.json().catch(() => ({}));
        setCreateError(d.detail || t('agrienergy.parks.createError'));
      }
    } catch {
      setCreateError(t('agrienergy.parks.createError'));
    } finally {
      setCreating(false);
    }
  };

  const selectTracker = (trackerId: string) => {
    viewer?.selectEntity?.(trackerId, 'AgriEnergyTracker');
  };

  const selectedPark = parks.find((p) => p.park_id === selectedParkId);
  const totalPower = trackerRows.reduce((sum, r) => sum + (r.power_w ?? 0), 0);
  const onlineCount = trackerRows.filter((r) => r.status === 'ok').length;

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Building2 size={16} className="text-blue-500" />
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            {t('agrienergy.parks.title')}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => fetchParks()}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title={t('agrienergy.parkOverview.refresh')}
          >
            <RefreshCw size={14} className="text-gray-400" />
          </button>
          <button
            type="button"
            onClick={() => {
              setShowCreateForm(!showCreateForm);
              setCreateError(null);
            }}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <Plus size={14} className={showCreateForm ? 'text-red-500' : 'text-blue-500'} />
          </button>
        </div>
      </div>

      {/* Create form */}
      {showCreateForm && (
        <Card className="bg-white dark:bg-gray-800 border border-blue-200 dark:border-blue-700">
          <div className="p-3 space-y-2">
            <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
              {t('agrienergy.parks.createPark')}
            </span>
            <input
              type="text"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder={t('agrienergy.parks.parkNamePlaceholder')}
              className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-xs text-gray-900 dark:text-gray-100"
            />
            <select
              value={createParcelId}
              onChange={(e) => setCreateParcelId(e.target.value)}
              className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-xs text-gray-900 dark:text-gray-100"
            >
              <option value="">{t('agrienergy.parks.selectParcel')}</option>
              {parcels.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            {parcels.length === 0 && (
              <p className="text-[10px] text-amber-600">{t('agrienergy.parks.noParcels')}</p>
            )}
            <Button
              size="sm"
              onClick={handleCreatePark}
              disabled={creating || !createName.trim() || !createParcelId.trim()}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs"
            >
              {creating ? t('common.loading') : t('agrienergy.parks.create')}
            </Button>
            {createError && <p className="text-[10px] text-red-600">{createError}</p>}
          </div>
        </Card>
      )}

      {/* Park selector */}
      {loadingParks && (
        <p className="text-xs text-gray-500 dark:text-gray-400">{t('common.loading')}</p>
      )}
      {!loadingParks && parks.length === 0 && !showCreateForm && (
        <Card className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
          <div className="p-4 text-center">
            <Building2 size={24} className="text-gray-300 dark:text-gray-600 mx-auto mb-2" />
            <p className="text-xs text-gray-500 dark:text-gray-400">{t('agrienergy.parks.noParks')}</p>
          </div>
        </Card>
      )}
      {!loadingParks && parks.length > 0 && (
        <select
          value={selectedParkId ?? ''}
          onChange={(e) => setSelectedParkId(e.target.value || null)}
          className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1.5 text-xs text-gray-900 dark:text-gray-100"
        >
          <option value="">{t('agrienergy.parks.selectPark')}</option>
          {parks.map((p) => (
            <option key={p.park_id} value={p.park_id}>
              {p.name} ({p.tracker_count} {t('agrienergy.parks.trackers')})
            </option>
          ))}
        </select>
      )}

      {/* Park summary cards */}
      {selectedPark && !loadingTrackers && trackerRows.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          <div className="flex flex-col items-center p-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
            <LayoutGrid size={14} className="text-blue-500 mb-1" />
            <span className="font-mono text-sm font-bold text-gray-900 dark:text-gray-100">
              {trackerRows.length}
            </span>
            <span className="text-[10px] text-gray-500 dark:text-gray-400">
              {t('agrienergy.parks.trackers')}
            </span>
          </div>
          <div className="flex flex-col items-center p-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
            <Zap size={14} className="text-emerald-500 mb-1" />
            <span className="font-mono text-sm font-bold text-emerald-600 dark:text-emerald-400">
              {totalPower >= 1000 ? (totalPower / 1000).toFixed(1) + 'k' : totalPower.toFixed(0)}
            </span>
            <span className="text-[10px] text-gray-500 dark:text-gray-400">W</span>
          </div>
          <div className="flex flex-col items-center p-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
            <span className="text-[10px] text-gray-500 dark:text-gray-400 mb-1">
              {t('agrienergy.parkOverview.online')}
            </span>
            <span className="font-mono text-sm font-bold text-gray-900 dark:text-gray-100">
              {onlineCount}/{trackerRows.length}
            </span>
            <StatusBadge
              status={onlineCount === trackerRows.length ? 'ok' : onlineCount > 0 ? 'warning' : 'critical'}
            />
          </div>
        </div>
      )}

      {/* Tracker table */}
      {selectedParkId && loadingTrackers && (
        <p className="text-xs text-gray-500 dark:text-gray-400">{t('common.loading')}</p>
      )}
      {selectedParkId && !loadingTrackers && trackerRows.length === 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400">{t('agrienergy.parks.noTrackersInPark')}</p>
      )}
      {selectedParkId && !loadingTrackers && trackerRows.length > 0 && (
        <Card className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-750 border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left px-2 py-1.5 font-medium text-gray-500 dark:text-gray-400">
                    {t('agrienergy.parkOverview.name')}
                  </th>
                  <th className="text-right px-2 py-1.5 font-medium text-gray-500 dark:text-gray-400">
                    {t('agrienergy.panel.tilt')}
                  </th>
                  <th className="text-right px-2 py-1.5 font-medium text-gray-500 dark:text-gray-400">
                    {t('agrienergy.panel.W')}
                  </th>
                  <th className="text-center px-2 py-1.5 font-medium text-gray-500 dark:text-gray-400">
                    {t('agrienergy.parkOverview.status')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {trackerRows.map((row) => (
                  <tr
                    key={row.tracker_id}
                    onClick={() => selectTracker(row.tracker_id)}
                    className="border-b border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                  >
                    <td className="px-2 py-1.5">
                      <span className="font-mono text-blue-600 dark:text-blue-400 hover:underline truncate block max-w-[120px]">
                        {row.name || row.tracker_id.split(':').pop()}
                      </span>
                    </td>
                    <td className="text-right px-2 py-1.5 font-mono text-gray-700 dark:text-gray-300">
                      {row.tilt != null ? `${row.tilt.toFixed(0)}${t('agrienergy.panel.deg')}` : '\u2014'}
                    </td>
                    <td className="text-right px-2 py-1.5 font-mono text-emerald-600 dark:text-emerald-400">
                      {row.power_w != null ? row.power_w.toFixed(0) : '\u2014'}
                    </td>
                    <td className="text-center px-2 py-1.5">
                      <StatusBadge status={row.status || 'offline'} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
