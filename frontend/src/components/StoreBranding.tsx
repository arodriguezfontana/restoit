import { useEffect } from 'react';
import { fetchStoreConfig } from '@/services/storeConfigService';
import { applyStoreBranding } from '@/utils/branding';

/**
 * Pone el nombre y el logo del local como título y favicon de la pestaña en cualquier pantalla (menú público, login
 * y panel). No muestra nada. Si no se puede cargar la configuración quedan los valores por defecto.
 */
export function StoreBranding() {
  useEffect(() => {
    let cancelled = false;
    fetchStoreConfig()
      .then((config) => {
        if (!cancelled) applyStoreBranding(config);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
