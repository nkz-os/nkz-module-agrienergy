import { defineModule } from '@nekazari/module-kit';
import './i18n';
import { moduleSlots } from './slots';
import pkg from '../package.json';

export default defineModule({
  id: 'agrienergy',
  displayName: 'AgriEnergy Orchestrator',
  version: pkg.version,
  hostApiVersion: '^2.0.0',
  description: 'Energy orchestration and solar tracker control — Nekazari Platform Module',
  accent: { base: '#F97316', soft: '#FFF7ED', strong: '#C2410C' },
  icon: 'zap',
  requiredPlan: 'premium',
  slots: moduleSlots as never,
});
