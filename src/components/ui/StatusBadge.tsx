/**
 * StatusBadge — Colored dot + label for status indication.
 */
import React from 'react';

type BadgeStatus = 'ok' | 'warning' | 'critical' | 'offline';

interface StatusBadgeProps {
  status: BadgeStatus;
  label?: string;
}

const STATUS_CONFIG: Record<BadgeStatus, { dot: string; text: string; bg: string }> = {
  ok: {
    dot: 'bg-emerald-500',
    text: 'text-emerald-700 dark:text-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-900/30',
  },
  warning: {
    dot: 'bg-amber-500',
    text: 'text-amber-700 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-900/30',
  },
  critical: {
    dot: 'bg-red-500',
    text: 'text-red-700 dark:text-red-400',
    bg: 'bg-red-50 dark:bg-red-900/30',
  },
  offline: {
    dot: 'bg-gray-400',
    text: 'text-gray-600 dark:text-gray-400',
    bg: 'bg-gray-100 dark:bg-gray-700/50',
  },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label }) => {
  const cfg = STATUS_CONFIG[status];
  return (
    <span
      className={
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium ' +
        cfg.bg + ' ' + cfg.text
      }
    >
      <span className={'w-1.5 h-1.5 rounded-full animate-pulse ' + cfg.dot} />
      {label || status}
    </span>
  );
};
