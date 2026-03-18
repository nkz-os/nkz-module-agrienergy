/**
 * ManualControls — Manual override buttons for tracker tilt/azimuth.
 * Sends overrides as static algorithm rules via PATCH /trackers/{id}/algorithm.
 */
import React, { useState } from 'react';
import { Button } from '@nekazari/ui-kit';
import { useTranslation } from '@nekazari/sdk';
import { ShieldAlert, Sun, SlidersHorizontal, Check, X } from 'lucide-react';

function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
}

interface ManualControlsProps {
  trackerId: string;
  currentTilt?: number;
  currentAzimuth?: number;
  onApplied?: () => void;
}

type ConfirmAction = 'stow' | 'track' | 'custom' | null;

export const ManualControls: React.FC<ManualControlsProps> = ({
  trackerId,
  currentTilt = 0,
  currentAzimuth = 180,
  onApplied,
}) => {
  const { t } = useTranslation();
  const [tilt, setTilt] = useState<number>(currentTilt);
  const [azimuth, setAzimuth] = useState<number>(currentAzimuth);
  const [confirming, setConfirming] = useState<ConfirmAction>(null);
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState<'ok' | 'error' | null>(null);

  const sendOverride = async (targetTilt: number, targetAzimuth: number) => {
    setSending(true);
    setFeedback(null);
    try {
      const res = await fetchWithAuth(
        `/api/agrienergy/trackers/${encodeURIComponent(trackerId)}/algorithm`,
        {
          method: 'PATCH',
          body: JSON.stringify({
            activeAlgorithm: {
              if: [true, { tilt: targetTilt, azimuth: targetAzimuth }],
            },
          }),
        }
      );
      if (res.ok) {
        setFeedback('ok');
        onApplied?.();
      } else {
        setFeedback('error');
      }
    } catch {
      setFeedback('error');
    } finally {
      setSending(false);
      setConfirming(null);
    }
  };

  const handleConfirm = () => {
    if (confirming === 'stow') {
      sendOverride(-60, currentAzimuth);
    } else if (confirming === 'track') {
      sendOverride(0, 180);
    } else if (confirming === 'custom') {
      sendOverride(tilt, azimuth);
    }
  };

  return (
    <div className="space-y-3">
      {/* Quick action buttons */}
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setConfirming('stow')}
          disabled={sending}
          className="flex flex-col items-center gap-1 p-2.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-red-50 dark:hover:bg-red-900/20 hover:border-red-300 dark:hover:border-red-700 transition-colors text-xs"
        >
          <ShieldAlert size={18} className="text-red-500" />
          <span className="font-medium text-gray-700 dark:text-gray-300">{t('agrienergy.manual.stow')}</span>
          <span className="text-[10px] text-gray-400">-60{t('agrienergy.panel.deg')}</span>
        </button>
        <button
          type="button"
          onClick={() => setConfirming('track')}
          disabled={sending}
          className="flex flex-col items-center gap-1 p-2.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:border-amber-300 dark:hover:border-amber-700 transition-colors text-xs"
        >
          <Sun size={18} className="text-amber-500" />
          <span className="font-medium text-gray-700 dark:text-gray-300">{t('agrienergy.manual.trackSun')}</span>
          <span className="text-[10px] text-gray-400">0{t('agrienergy.panel.deg')} / 180{t('agrienergy.panel.deg')}</span>
        </button>
      </div>

      {/* Custom override */}
      <div className="p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 space-y-2">
        <div className="flex items-center gap-1.5">
          <SlidersHorizontal size={14} className="text-blue-500" />
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
            {t('agrienergy.manual.customOverride')}
          </span>
        </div>

        {/* Tilt slider */}
        <div>
          <div className="flex justify-between text-[10px] text-gray-500 dark:text-gray-400 mb-0.5">
            <span>{t('agrienergy.panel.tilt')}</span>
            <span className="font-mono font-semibold text-gray-700 dark:text-gray-300">{tilt}{t('agrienergy.panel.deg')}</span>
          </div>
          <input
            type="range"
            min={-60}
            max={60}
            step={1}
            value={tilt}
            onChange={(e) => setTilt(Number(e.target.value))}
            className="w-full h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full appearance-none cursor-pointer accent-blue-500"
          />
          <div className="flex justify-between text-[9px] text-gray-400">
            <span>-60{t('agrienergy.panel.deg')}</span>
            <span>0{t('agrienergy.panel.deg')}</span>
            <span>60{t('agrienergy.panel.deg')}</span>
          </div>
        </div>

        {/* Azimuth slider */}
        <div>
          <div className="flex justify-between text-[10px] text-gray-500 dark:text-gray-400 mb-0.5">
            <span>{t('agrienergy.panel.azimuth')}</span>
            <span className="font-mono font-semibold text-gray-700 dark:text-gray-300">{azimuth}{t('agrienergy.panel.deg')}</span>
          </div>
          <input
            type="range"
            min={0}
            max={360}
            step={1}
            value={azimuth}
            onChange={(e) => setAzimuth(Number(e.target.value))}
            className="w-full h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full appearance-none cursor-pointer accent-blue-500"
          />
          <div className="flex justify-between text-[9px] text-gray-400">
            <span>0{t('agrienergy.panel.deg')} N</span>
            <span>180{t('agrienergy.panel.deg')} S</span>
            <span>360{t('agrienergy.panel.deg')} N</span>
          </div>
        </div>

        <Button
          onClick={() => setConfirming('custom')}
          disabled={sending}
          size="sm"
          className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs"
        >
          {t('agrienergy.manual.applyCustom')}
        </Button>
      </div>

      {/* Confirmation dialog */}
      {confirming && (
        <div className="p-3 rounded-lg border-2 border-amber-400 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/30 space-y-2">
          <p className="text-xs font-medium text-amber-800 dark:text-amber-300">
            {confirming === 'stow' && t('agrienergy.manual.confirmStow')}
            {confirming === 'track' && t('agrienergy.manual.confirmTrack')}
            {confirming === 'custom' &&
              t('agrienergy.manual.confirmCustom', {
                tilt: String(tilt),
                azimuth: String(azimuth),
              })}
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={handleConfirm}
              disabled={sending}
              className="flex-1 bg-amber-600 hover:bg-amber-700 text-white text-xs"
            >
              <Check size={14} className="mr-1 inline" />
              {sending ? t('common.loading') : t('agrienergy.manual.confirm')}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setConfirming(null)}
              disabled={sending}
              className="flex-1 text-xs"
            >
              <X size={14} className="mr-1 inline" />
              {t('agrienergy.parks.cancel')}
            </Button>
          </div>
        </div>
      )}

      {/* Feedback */}
      {feedback === 'ok' && (
        <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
          {t('agrienergy.manual.overrideSent')}
        </p>
      )}
      {feedback === 'error' && (
        <p className="text-xs text-red-600 dark:text-red-400 font-medium">
          {t('agrienergy.manual.overrideError')}
        </p>
      )}
    </div>
  );
};
