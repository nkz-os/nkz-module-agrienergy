/**
 * IIFE entry point — called when the host injects this bundle via <script>.
 * Must call window.__NKZ__.register() to activate the module.
 *
 * MODULE_ID must match the `id` column in marketplace_modules exactly.
 */
import { moduleSlots } from './slots';
import { i18n } from '@nekazari/sdk';
import pkg from '../package.json';
import esTranslations from './locales/es.json';
import enTranslations from './locales/en.json';

const MODULE_ID = 'agrienergy';

if (typeof window !== 'undefined' && window.__NKZ__) {
  // Register module translations into the default namespace (deep merge)
  if (i18n && i18n.addResourceBundle) {
    i18n.addResourceBundle('es', 'translation', esTranslations, true, true);
    i18n.addResourceBundle('en', 'translation', enTranslations, true, true);
  }

  window.__NKZ__.register({
    id: MODULE_ID,
    viewerSlots: moduleSlots,
    version: pkg.version,
  });
}
