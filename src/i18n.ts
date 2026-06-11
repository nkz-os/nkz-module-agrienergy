import { i18n } from '@nekazari/sdk';
import ca from './locales/ca.json';
import en from './locales/en.json';
import es from './locales/es.json';
import eu from './locales/eu.json';
import fr from './locales/fr.json';
import pt from './locales/pt.json';

const NS = 'common';

const BUNDLES: Record<string, typeof en> = { ca, en, es, eu, fr, pt };

function register(): void {
  const add = i18n && 'addResourceBundle' in i18n ? i18n.addResourceBundle : undefined;
  if (typeof add !== 'function') return;
  for (const [lang, bundle] of Object.entries(BUNDLES)) {
    add.call(i18n, lang, NS, bundle, true, true);
  }
}

register();
