/**
 * Slot definitions — declare which host slots this module occupies.
 *
 * Available slots:
 *   map-layer      — overlay or toolbar button on the 3D map
 *   layer-toggle   — toggle entry in the layer panel
 *   context-panel  — side panel shown when an entity is selected
 *   bottom-panel   — tabbed panel at the bottom of the viewer
 *   entity-tree    — context menu entry in the entity tree
 *   dashboard-widget — card in the tenant dashboard
 */
import { AgriEnergySandbox } from '../components/sandbox/AgriEnergySandbox';

const MODULE_ID = 'agrienergy';

interface SlotWidgetDefinition {
  id: string;
  moduleId: string;
  component: string;
  localComponent?: React.ComponentType<any>;
  priority: number;
  showWhen?: { entityType?: string[]; layerActive?: string[] };
  defaultProps?: Record<string, unknown>;
}

type ModuleViewerSlots = Record<string, SlotWidgetDefinition[]>;

export const moduleSlots: ModuleViewerSlots = {
  'map-layer': [],
  'layer-toggle': [],
  'context-panel': [
    {
      id: 'agrienergy-context',
      moduleId: MODULE_ID,
      component: 'AgriEnergySandbox',
      localComponent: AgriEnergySandbox,
      priority: 10,
    },
  ],
  'bottom-panel': [],
  'entity-tree': [],
  'dashboard-widget': [],
};
