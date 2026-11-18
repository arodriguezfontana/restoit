import { useEffect } from 'react';
import { CashPinSection } from '@/components/configuracion/CashPinSection';
import { LoginBackgroundSection } from '@/components/configuracion/LoginBackgroundSection';
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

export function ConfiguracionWebView({ onConfigUpdated }: ConfiguracionWebViewProps = {}) {
  const form = useStoreSettingsForm(onConfigUpdated);
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

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-16">
      <Toast message={feedback?.message ?? null} type={feedback?.type} onClose={() => setFeedback(null)} />
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-5 rounded-2xl shadow-xs border border-gray-100">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Configuración</h1>
          <p className="text-sm text-gray-500 mt-1">
            Identidad visual, datos del local, medios de pago y seguridad.
          </p>
        </div>
      </div>

      <form onSubmit={form.handleSubmit} className="space-y-6">
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
        <PaymentMethodsSection
          payments={form.payments}
          setPayments={form.setPayments}
          mercadopagoAvailable={form.mercadopagoAvailable}
        />
        <CashPinSection
          cashPinEnabled={form.cashPinEnabled}
          setCashPinEnabled={form.setCashPinEnabled}
          cashPin={form.cashPin}
          setCashPin={form.setCashPin}
          clearFeedback={() => form.setFeedback(null)}
        />

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
    </div>
  );
}
