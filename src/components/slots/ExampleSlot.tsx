/**
 * ExampleSlot — replace with your actual slot component.
 *
 * Slot components render inside host-provided containers.
 * - Access viewer context via useViewer() and useAuth() from @nekazari/sdk
 * - React, SDK and UI-Kit are externalized — they come from the host via window globals.
 * - Keep panels responsive (300–600px wide).
 * - Use SlotShell or SlotShellCompact from @nekazari/viewer-kit for consistent styling.
 * - Use ui-kit components (Button, Badge, Spinner, etc.) and design token classes
 *   (text-nkz-*, bg-nkz-*) for themed appearance.
 */

import React, { useState } from 'react';
import { useViewer, useAuth } from '@nekazari/sdk';
import { SlotShellCompact } from '@nekazari/viewer-kit';
import { AlertCircle, RefreshCw } from 'lucide-react';

const agrienergyAccent = { base: '#F97316', soft: '#FFF7ED', strong: '#C2410C' };

interface ExampleSlotProps {
  className?: string;
}

export const ExampleSlot: React.FC<ExampleSlotProps> = ({ className: _className }) => {
  const { selectedEntityId } = useViewer();
  const { isAuthenticated, user } = useAuth();
  const [loading, setLoading] = useState(false);

  if (!isAuthenticated) {
    return (
      <SlotShellCompact moduleId="agrienergy" accent={agrienergyAccent}>
        <div className="flex items-center gap-nkz-inline text-nkz-warning p-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span className="text-nkz-sm text-nkz-text-muted">Authentication required.</span>
        </div>
      </SlotShellCompact>
    );
  }

  return (
    <SlotShellCompact moduleId="agrienergy" accent={agrienergyAccent}>
      <div className="space-y-nkz-stack">
        <div className="flex items-center justify-between">
          <h3 className="text-nkz-sm font-semibold text-nkz-text-primary">AgriEnergy Orchestrator</h3>
          <button
            onClick={() => setLoading(l => !l)}
            className="p-1 rounded hover:bg-nkz-bg-soft text-nkz-text-muted"
            aria-label="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="text-nkz-xs text-nkz-text-muted space-y-nkz-stack bg-nkz-bg-soft rounded p-2">
          <div className="flex justify-between gap-nkz-inline">
            <span>Entity:</span>
            <span className="font-mono text-nkz-text-secondary truncate">{selectedEntityId ?? '—'}</span>
          </div>
          <div className="flex justify-between gap-nkz-inline">
            <span>User:</span>
            <span className="text-nkz-text-secondary truncate">{user?.email ?? '—'}</span>
          </div>
        </div>

        <p className="text-nkz-xs text-nkz-text-muted italic">
          Replace this component with your module functionality.
        </p>
      </div>
    </SlotShellCompact>
  );
};

export default ExampleSlot;
