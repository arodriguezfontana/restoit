import { useEffect, useState } from 'react';
import { CashPinSection } from '@/components/configuracion/CashPinSection';
import { CouponsSection } from '@/components/configuracion/CouponsSection';
import { DelaySettingsSection } from '@/components/configuracion/DelaySettingsSection';
import { LoginBackgroundSection } from '@/components/configuracion/LoginBackgroundSection';
import { MenuBackgroundSection } from '@/components/configuracion/MenuBackgroundSection';
import { LogoSection } from '@/components/configuracion/LogoSection';
import { PaymentMethodsSection } from '@/components/configuracion/PaymentMethodsSection';
import { PanelBackgroundSection } from '@/components/configuracion/PanelBackgroundSection';
import { StoreDataSection } from '@/components/configuracion/StoreDataSection';
import { StorePreviewSection } from '@/components/configuracion/StorePreviewSection';
import { ThemeColorSection } from '@/components/configuracion/ThemeColorSection';
import { Toast } from '@/components/ui/Toast';
import { PanelNote } from '@/components/ui/PanelNote';
import { useStoreSettingsForm } from '@/hooks/useStoreSettingsForm';
import { getThemeOption } from '@/types/storeConfig';
import type { StoreConfig } from '@/types/storeConfig';

interface ConfiguracionWebViewProps {
  onConfigUpdated?: (config: StoreConfig) => void;
}

type ConfigTab = 'local' | 'apariencia' | 'pagos' | 'demoras' | 'cupones' | 'seguridad';

const TABS: { id: ConfigTab; label: string; description: string }[] = [
  { id: 'local', label: 'Local', description: 'Nombre, contacto y logo.' },
  { id: 'demoras', label: 'Demoras', description: 'Cómo se calcula la demora de los pedidos.' },
  { id: 'cupones', label: 'Cupones', description: 'Cupones de descuento exclusivos para la web.' },
  { id: 'pagos', label: 'Medios de pago', description: 'Cómo cobra el local.' },
  { id: 'apariencia', label: 'Apariencia', description: 'Colores y fondos del panel, el menú y el login.' },
  { id: 'seguridad', label: 'Seguridad', description: 'PIN de la caja.' },
];

export function ConfiguracionWebView({ onConfigUpdated }: ConfiguracionWebViewProps = {}) {
  const form = useStoreSettingsForm(onConfigUpdated);
  const [activeTab, setActiveTab] = useState<ConfigTab>('local');
  const currentTheme = getThemeOption(form.themeColor);
  const { feedback, setFeedback } = form;

  // El aviso aparece arriba a la derecha y se va solo (los errores quedan más tiempo para poder leerlos).
  useEffect(() => {
    if (!feedback) return;
    const timer = setTimeout(() => setFeedback(null), feedback.type === 'error' ? 8000 : 5000);
    return () => clearTimeout(timer);
  }, [feedback, setFeedback]);

  if (form.loading) {
    return <PanelNote>Cargando configuración...</PanelNote>;
  }

  // Las demoras y los cupones se gestionan al instante, por eso no forman parte del formulario ni muestran "Guardar cambios".
  const isFormTab = activeTab !== 'demoras' && activeTab !== 'cupones';
  const activeDescription = TABS.find((tab) => tab.id === activeTab)?.description;

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-16">
      <Toast message={feedback?.message ?? null} type={feedback?.type} onClose={() => setFeedback(null)} />
      <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Configuración</h1>
          <p className="text-sm text-gray-500 mt-1">{activeDescription}</p>
        </div>
        <div role="tablist" aria-label="Secciones de configuración" className="flex flex-wrap gap-2">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`config-tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls="config-tabpanel"
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-xl text-sm font-semibold transition ${
                activeTab === tab.id ? 'bg-zinc-900 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div id="config-tabpanel" role="tabpanel" aria-labelledby={`config-tab-${activeTab}`}>
        {activeTab === 'demoras' && <DelaySettingsSection />}
        {activeTab === 'cupones' && <CouponsSection />}

        {isFormTab && (
          <form onSubmit={form.handleSubmit} className="space-y-6">
            {activeTab === 'local' && (
              <>
                <StoreDataSection
                  storeName={form.storeName}
                  setStoreName={form.setStoreName}
                  contactPhone={form.contactPhone}
                  setContactPhone={form.setContactPhone}
                  address={form.address}
                  setAddress={form.setAddress}
                />
                <LogoSection
                  logoUrl={form.logoUrl}
                  fileInputRef={form.fileInputRef}
                  handleFileChange={form.handleFileChange}
                  handleRemoveLogo={form.handleRemoveLogo}
                />
              </>
            )}
            {activeTab === 'apariencia' && (
              <>
                <ThemeColorSection
                  themeColor={form.themeColor}
                  setThemeColor={form.setThemeColor}
                  colorInputRef={form.colorInputRef}
                />
                <StorePreviewSection
                  currentTheme={currentTheme}
                  logoUrl={form.logoUrl}
                  storeName={form.storeName}
                  address={form.address}
                  contactPhone={form.contactPhone}
                />
                <LoginBackgroundSection
                  loginBg={form.loginBg}
                  setLoginBg={form.setLoginBg}
                  loginBgImage={form.loginBgImage}
                  bgFileInputRef={form.bgFileInputRef}
                  handleBgFileChange={form.handleBgFileChange}
                  handleRemoveBgImage={form.handleRemoveBgImage}
                  currentTheme={currentTheme}
                />
                <PanelBackgroundSection
                  panelBg={form.panelBg}
                  setPanelBg={form.setPanelBg}
                  panelBgImage={form.panelBgImage}
                  setPanelBgImage={form.setPanelBgImage}
                  panelBgColor={form.panelBgColor}
                  setPanelBgColor={form.setPanelBgColor}
                  currentTheme={currentTheme}
                  onError={(message) => form.setFeedback(message ? { type: 'error', message } : null)}
                />
                <MenuBackgroundSection
                  menuBg={form.menuBg}
                  setMenuBg={form.setMenuBg}
                  menuBgImage={form.menuBgImage}
                  setMenuBgImage={form.setMenuBgImage}
                  menuBgColor={form.menuBgColor}
                  setMenuBgColor={form.setMenuBgColor}
                  currentTheme={currentTheme}
                  onError={(message) => form.setFeedback(message ? { type: 'error', message } : null)}
                />
              </>
            )}
            {activeTab === 'pagos' && (
              <PaymentMethodsSection
                payments={form.payments}
                setPayments={form.setPayments}
                mercadopagoAvailable={form.mercadopagoAvailable}
              />
            )}
            {activeTab === 'seguridad' && (
              <CashPinSection
                cashPinEnabled={form.cashPinEnabled}
                setCashPinEnabled={form.setCashPinEnabled}
                cashPin={form.cashPin}
                setCashPin={form.setCashPin}
                clearFeedback={() => form.setFeedback(null)}
              />
            )}

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={form.saving}
                style={{ backgroundColor: currentTheme.hex }}
                className="px-6 py-3 rounded-xl text-white font-bold text-sm tracking-wide transition shadow-sm hover:opacity-90 disabled:opacity-50"
              >
                {form.saving ? 'Guardando cambios...' : 'Guardar cambios'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
