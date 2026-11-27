import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, SubmitEvent } from 'react';
import { fetchStoreConfig, updateStoreConfig } from '@/services/storeConfigService';
import type { CardAppliesTo, LoginBgOption, PanelBgOption, StoreConfig, ThemeColor } from '@/types/storeConfig';
import { getErrorMessage } from '@/utils/errors';
import { resizeImageToDataUrl } from '@/utils/images';
import { applyThemeColor } from '@/utils/theme';

const MAX_LOGO_BYTES = 2 * 1024 * 1024;
// La imagen de fondo se achica antes de guardarla, así que se acepta una foto pesada del celular.
const MAX_BACKGROUND_BYTES = 15 * 1024 * 1024;

/** Los medios de pago que acepta el local y sus datos de cobro. */
export interface PaymentSettings {
  acceptsCash: boolean;
  acceptsTransfer: boolean;
  transferAlias: string;
  transferCbu: string;
  transferHolder: string;
  acceptsCard: boolean;
  cardAppliesTo: CardAppliesTo;
  acceptsMercadopago: boolean;
  /** Horas que se guarda el comprobante de una transferencia (texto del campo). */
  proofRetentionHours: string;
}

function paymentSettingsFrom(config: StoreConfig): PaymentSettings {
  return {
    acceptsCash: config.accepts_cash ?? true,
    acceptsTransfer: Boolean(config.accepts_transfer),
    transferAlias: config.transfer_alias || '',
    transferCbu: config.transfer_cbu || '',
    transferHolder: config.transfer_holder || '',
    acceptsCard: Boolean(config.accepts_card),
    cardAppliesTo: config.card_applies_to || 'both',
    // Sin credenciales no se puede cobrar por MercadoPago, aunque haya quedado activado.
    acceptsMercadopago: Boolean(config.accepts_mercadopago) && Boolean(config.mercadopago_available),
    proofRetentionHours: String(config.proof_retention_hours ?? 48),
  };
}

/** El primer problema de los medios de pago, o null si están bien (el servidor valida lo mismo). */
function paymentsProblem(payments: PaymentSettings): string | null {
  const { acceptsCash, acceptsTransfer, acceptsCard, acceptsMercadopago } = payments;
  if (!(acceptsCash || acceptsTransfer || acceptsCard || acceptsMercadopago)) return 'Tiene que haber al menos un medio de pago activo.';
  if (acceptsTransfer && !(payments.transferAlias.trim() || payments.transferCbu.trim())) {
    return 'Para aceptar transferencias cargá el alias o el CBU.';
  }
  if (acceptsTransfer && !payments.transferHolder.trim()) return 'Para aceptar transferencias cargá el titular de la cuenta.';
  const hours = Number(payments.proofRetentionHours);
  if (acceptsTransfer && !(Number.isInteger(hours) && hours >= 1 && hours <= 720)) {
    return 'Las horas que se guarda el comprobante tienen que ser un número entre 1 y 720.';
  }
  return null;
}

export type Feedback = { type: 'success' | 'error'; message: string } | null;

/** Valores del formulario a partir de la configuración guardada (con los valores por defecto donde falte algo). */
function formValuesFrom(config: StoreConfig) {
  return {
    storeName: config.store_name || 'RestoIT',
    address: config.address || '',
    contactPhone: config.contact_phone || '',
    logoUrl: config.logo_url || null,
    themeColor: config.theme_color || 'black',
    loginBg: config.login_bg || 'bistro',
    loginBgImage: config.login_bg_image || null,
    panelBg: config.panel_bg || 'none',
    panelBgImage: config.panel_bg_image || null,
    panelBgColor: config.panel_bg_color || null,
    menuBg: config.menu_bg || 'none',
    menuBgImage: config.menu_bg_image || null,
    menuBgColor: config.menu_bg_color || null,
    mpAlias: config.mp_alias || '',
    payments: paymentSettingsFrom(config),
    cashPinEnabled: Boolean(config.cash_pin_enabled),
    cashPin: config.cash_pin || '',
  };
}

/** El texto de un error del servidor o de validación de una imagen subida, o null si el archivo es válido. */
function imageProblem(file: File, maxBytes: number, maxText: string, formats: string): string | null {
  if (!file.type.startsWith('image/')) return `Por favor seleccioná un archivo de imagen válido (${formats}).`;
  return file.size > maxBytes ? maxText : null;
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => (typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Sin datos')));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** El formulario de configuración del local: lo carga, valida los archivos que se suben y guarda los cambios. */
export function useStoreSettingsForm(onConfigUpdated?: (config: StoreConfig) => void) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const [storeName, setStoreName] = useState('RestoIT');
  const [address, setAddress] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [themeColor, setThemeColor] = useState<ThemeColor>('black');
  const [loginBg, setLoginBg] = useState<LoginBgOption>('bistro');
  const [loginBgImage, setLoginBgImage] = useState<string | null>(null);
  const [panelBg, setPanelBg] = useState<PanelBgOption>('none');
  const [panelBgImage, setPanelBgImage] = useState<string | null>(null);
  const [panelBgColor, setPanelBgColor] = useState<string | null>(null);
  const [menuBg, setMenuBg] = useState<PanelBgOption>('none');
  const [menuBgImage, setMenuBgImage] = useState<string | null>(null);
  const [menuBgColor, setMenuBgColor] = useState<string | null>(null);
  const [mpAlias, setMpAlias] = useState('');
  const [payments, setPayments] = useState<PaymentSettings>(() => paymentSettingsFrom({} as StoreConfig));
  const [mercadopagoAvailable, setMercadopagoAvailable] = useState(false);
  const [cashPinEnabled, setCashPinEnabled] = useState(false);
  const [cashPin, setCashPin] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const colorInputRef = useRef<HTMLInputElement>(null);
  const bgFileInputRef = useRef<HTMLInputElement>(null);

  const showConfig = (config: StoreConfig) => {
    const values = formValuesFrom(config);
    setStoreName(values.storeName);
    setAddress(values.address);
    setContactPhone(values.contactPhone);
    setLogoUrl(values.logoUrl);
    setThemeColor(values.themeColor);
    setLoginBg(values.loginBg);
    setLoginBgImage(values.loginBgImage);
    setPanelBg(values.panelBg);
    setPanelBgImage(values.panelBgImage);
    setPanelBgColor(values.panelBgColor);
    setMenuBg(values.menuBg);
    setMenuBgImage(values.menuBgImage);
    setMenuBgColor(values.menuBgColor);
    setMpAlias(values.mpAlias);
    setPayments(values.payments);
    setMercadopagoAvailable(Boolean(config.mercadopago_available));
    setCashPinEnabled(values.cashPinEnabled);
    setCashPin(values.cashPin);
    applyThemeColor(values.themeColor);
  };

  useEffect(() => {
    let cancelled = false;
    fetchStoreConfig()
      .then((data: StoreConfig) => {
        if (!cancelled) showConfig(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setFeedback({ type: 'error', message: getErrorMessage(err, 'No se pudo cargar la configuración actual.') });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const showError = (message: string) => setFeedback({ type: 'error', message });

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const problem = imageProblem(file, MAX_LOGO_BYTES, 'La imagen no debe superar los 2 MB.', 'PNG, JPG, SVG, WebP');
    if (problem) {
      showError(problem);
      return;
    }
    setLogoUrl(await readAsDataUrl(file));
    setFeedback(null);
  };

  const handleBgFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const problem = imageProblem(file, MAX_BACKGROUND_BYTES, 'La imagen de fondo no debe superar los 15 MB.', 'PNG, JPG o WebP');
    if (problem) {
      showError(problem);
      return;
    }
    try {
      setLoginBgImage(await resizeImageToDataUrl(file));
      setLoginBg('custom');
      setFeedback(null);
    } catch {
      showError('No se pudo leer la imagen seleccionada.');
    }
  };

  const handleRemoveBgImage = () => {
    setLoginBgImage(null);
    if (loginBg === 'custom') setLoginBg('bistro');
  };

  const handleRemoveLogo = () => {
    setLogoUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  /** El primer problema de los datos a guardar, o null si están bien. */
  const validationError = (): string | null => {
    if (!storeName.trim()) return 'El nombre del local es obligatorio.';
    if (cashPinEnabled && !/^\d{4}$/.test(cashPin)) return 'El PIN de caja debe tener exactamente 4 dígitos numéricos.';
    return paymentsProblem(payments);
  };

  const handleSubmit = async (event: SubmitEvent) => {
    event.preventDefault();
    const problem = validationError();
    if (problem) {
      showError(problem);
      return;
    }

    setSaving(true);
    setFeedback(null);
    try {
      const updated = await updateStoreConfig({
        store_name: storeName.trim(),
        address: address.trim() || null,
        contact_phone: contactPhone.trim() || null,
        logo_url: logoUrl,
        theme_color: themeColor,
        login_bg: loginBg,
        login_bg_image: loginBgImage,
        panel_bg: panelBg,
        panel_bg_image: panelBgImage,
        panel_bg_color: panelBgColor,
        menu_bg: menuBg,
        menu_bg_image: menuBgImage,
        menu_bg_color: menuBgColor,
        mp_alias: mpAlias.trim() || null,
        accepts_cash: payments.acceptsCash,
        accepts_transfer: payments.acceptsTransfer,
        transfer_alias: payments.acceptsTransfer ? payments.transferAlias.trim() || null : null,
        transfer_cbu: payments.acceptsTransfer ? payments.transferCbu.trim() || null : null,
        transfer_holder: payments.acceptsTransfer ? payments.transferHolder.trim() || null : null,
        accepts_card: payments.acceptsCard,
        card_applies_to: payments.cardAppliesTo,
        accepts_mercadopago: payments.acceptsMercadopago,
        proof_retention_hours: Number(payments.proofRetentionHours) || 48,
        cash_pin_enabled: cashPinEnabled,
        cash_pin: cashPinEnabled ? cashPin : null,
      });
      showConfig(updated);
      setFeedback({ type: 'success', message: '¡Configuración guardada exitosamente!' });
      onConfigUpdated?.(updated);
    } catch (err) {
      showError(getErrorMessage(err, 'Ocurrió un error al guardar los cambios.'));
    } finally {
      setSaving(false);
    }
  };

  return {
    loading,
    saving,
    feedback,
    setFeedback,
    storeName,
    setStoreName,
    address,
    setAddress,
    contactPhone,
    setContactPhone,
    logoUrl,
    themeColor,
    setThemeColor,
    loginBg,
    setLoginBg,
    loginBgImage,
    panelBg,
    setPanelBg,
    panelBgImage,
    setPanelBgImage,
    panelBgColor,
    setPanelBgColor,
    menuBg,
    setMenuBg,
    menuBgImage,
    setMenuBgImage,
    menuBgColor,
    setMenuBgColor,
    mpAlias,
    payments,
    setPayments,
    mercadopagoAvailable,
    cashPinEnabled,
    setCashPinEnabled,
    cashPin,
    setCashPin,
    fileInputRef,
    colorInputRef,
    bgFileInputRef,
    handleFileChange,
    handleBgFileChange,
    handleRemoveBgImage,
    handleRemoveLogo,
    handleSubmit,
  };
}
