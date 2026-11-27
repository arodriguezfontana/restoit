import backgroundBistro from '@/assets/background_bistro.jpg';
import backgroundKitchen from '@/assets/background_kitchen.jpg';
import backgroundTrattoria from '@/assets/background_trattoria.jpg';
import type { PanelBgOption, StoreConfig } from '@/types/storeConfig';

/** Imágenes incluidas que se pueden elegir de fondo del panel (las mismas que para el inicio de sesión). */
export const PANEL_BG_PRESETS: { id: Exclude<PanelBgOption, 'none' | 'color' | 'custom'>; name: string; image: string }[] = [
  { id: 'bistro', name: 'Salón', image: backgroundBistro },
  { id: 'kitchen', name: 'Cocina', image: backgroundKitchen },
  { id: 'trattoria', name: 'Platos', image: backgroundTrattoria },
];

/** Color con el que arranca el selector de color de fondo (gris azulado oscuro). */
export const DEFAULT_PANEL_COLOR = '#334155';

export interface PanelBackground {
  /** Valor de la propiedad CSS background-image. */
  css: string;
  /** Las fotos se desenfocan; el color liso no lo necesita. */
  blurred: boolean;
}

const VEIL = 'linear-gradient(rgb(15 23 42 / 0.55), rgb(15 23 42 / 0.55))';

/** Fondo del panel según la configuración del local; null = fondo liso por defecto. */
export function panelBackground(
  config: Pick<StoreConfig, 'panel_bg' | 'panel_bg_image' | 'panel_bg_color'> | null
): PanelBackground | null {
  return resolveBackground(config?.panel_bg, config?.panel_bg_image, config?.panel_bg_color);
}

/** Fondo de la página pública /menu según la configuración del local; null = fondo liso por defecto. */
export function menuBackground(
  config: Pick<StoreConfig, 'menu_bg' | 'menu_bg_image' | 'menu_bg_color'> | null
): PanelBackground | null {
  return resolveBackground(config?.menu_bg, config?.menu_bg_image, config?.menu_bg_color);
}

function resolveBackground(
  choice: PanelBgOption | undefined,
  customImage: string | null | undefined,
  customColor: string | null | undefined
): PanelBackground | null {
  if (!choice || choice === 'none') return null;
  // Un color se pinta como un degradado de un solo tono: así todos los fondos usan la misma propiedad.
  if (choice === 'color') {
    const color = customColor;
    return color ? { css: `linear-gradient(${color}, ${color})`, blurred: false } : null;
  }
  const image =
    choice === 'custom' ? customImage || null : (PANEL_BG_PRESETS.find((preset) => preset.id === choice)?.image ?? null);
  // Velo oscuro sobre la foto: todo texto de las secciones va sobre una tarjeta blanca.
  return image ? { css: `${VEIL}, url("${image}")`, blurred: true } : null;
}
