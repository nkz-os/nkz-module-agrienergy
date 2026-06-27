/** Context keys exposed in ConfigureSignals — must match JSON Logic var paths in backend presets. */
export const DEFAULT_SIGNAL_CONTEXT_KEYS = [
  'weather.ghi',
  'weather.dni',
  'weather.dhi',
  'weather.temperature',
  'weather.wind_speed',
  'weather.humidity',
  'sensors.leaf_temperature',
  'sensors.par_under_panel',
] as const;

/** Legacy UI keys persisted on trackers before contract alignment. */
export const LEGACY_SIGNAL_KEY_MAP: Record<string, string> = {
  'crop.leaf_temperature': 'sensors.leaf_temperature',
  'crop.par': 'sensors.par_under_panel',
};

export function normalizeSignalContextKey(key: string): string {
  return LEGACY_SIGNAL_KEY_MAP[key] ?? key;
}
