import { PanelBgPicker } from '@/components/PanelBgPicker';
import type { PanelBgOption, ThemeOption } from '@/types/storeConfig';

interface MenuBackgroundSectionProps {
  menuBg: PanelBgOption;
  setMenuBg: (option: PanelBgOption) => void;
  menuBgImage: string | null;
  setMenuBgImage: (image: string | null) => void;
  menuBgColor: string | null;
  setMenuBgColor: (color: string | null) => void;
  currentTheme: ThemeOption;
  onError: (message: string | null) => void;
}

/** Fondo de la página pública /menu: liso, un color, una imagen o una propia. */
export function MenuBackgroundSection({ menuBg, setMenuBg, menuBgImage, setMenuBgImage, menuBgColor, setMenuBgColor, currentTheme, onError }: MenuBackgroundSectionProps) {
  return (
    <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-4">
      <div>
        <h2 className="text-base font-bold text-gray-900">Fondo del Menú</h2>
        <p className="text-xs text-gray-500 mt-1">
          Color o imagen de fondo de la página donde tus clientes arman su pedido.
        </p>
      </div>
      <PanelBgPicker
        target="menú"
        value={menuBg}
        image={menuBgImage}
        color={menuBgColor}
        accentColor={currentTheme.hex}
        onChange={setMenuBg}
        onImageChange={setMenuBgImage}
        onColorChange={setMenuBgColor}
        onError={onError}
      />
    </section>
  );
}
