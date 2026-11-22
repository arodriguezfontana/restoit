import type { StoreConfig } from '@/types/storeConfig';
import { buildFaviconFromLogo } from '@/utils/faviconImage';

const DEFAULT_TITLE = 'RestoIT';
const DEFAULT_FAVICON = '/favicon-restoit.png';
const DEFAULT_FAVICON_TYPE = 'image/png';

type Branding = Pick<StoreConfig, 'store_name' | 'logo_url'>;

/** Cuenta cada cambio de logo: el favicon que termina de procesarse tarde no pisa a uno más nuevo. */
let faviconVersion = 0;

/** El tipo de imagen de un logo guardado como Data URL ("data:image/png;base64,..."); vacío si no se puede saber. */
function imageTypeOf(url: string): string | null {
  const match = /^data:(image\/[a-z0-9.+-]+)[;,]/i.exec(url);
  return match ? match[1] : null;
}

function faviconLink(): HTMLLinkElement {
  let link = document.querySelector<HTMLLinkElement>('link[rel~="icon"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  return link;
}

/**
 * Pone el nombre del local como título de la pestaña y su logo como favicon. Sin nombre o sin logo (o sin
 * configuración) se usan los de RestoIT.
 */
export function applyStoreBranding(config: Branding | null | undefined) {
  if (typeof document === 'undefined') return;

  document.title = config?.store_name?.trim() || DEFAULT_TITLE;

  const link = faviconLink();
  const logo = config?.logo_url?.trim();
  const version = ++faviconVersion;
  if (!logo) {
    link.href = DEFAULT_FAVICON;
    link.type = DEFAULT_FAVICON_TYPE;
    return;
  }
  link.href = logo;
  const type = imageTypeOf(logo);
  if (type) link.type = type;
  else link.removeAttribute('type');

  // Mientras tanto se ve el logo tal cual; al terminar se reemplaza por el favicon sin fondo blanco y con contorno.
  void buildFaviconFromLogo(logo).then((favicon) => {
    if (!favicon || version !== faviconVersion) return;
    link.href = favicon;
    link.type = 'image/png';
  });
}
