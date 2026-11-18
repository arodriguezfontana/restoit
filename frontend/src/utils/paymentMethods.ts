import type { DeliveryMethod, PaymentMethod } from '@/types/order';
import type { StoreConfig } from '@/types/storeConfig';

/** Mientras no se conoce la configuración del local, solo se ofrece efectivo. */
const FALLBACK_METHODS: PaymentMethod[] = ['efectivo'];

/**
 * Medios con los que se puede pagar un pedido según lo que el local habilitó (igual que el servidor, que además
 * rechaza cualquier otro). La tarjeta puede valer solo para retiro o solo para envío.
 */
export function acceptedPaymentMethods(config: StoreConfig | null, delivery?: DeliveryMethod): PaymentMethod[] {
  if (!config) return FALLBACK_METHODS;
  const methods: PaymentMethod[] = [];
  if (config.accepts_cash ?? true) methods.push('efectivo');
  if (config.accepts_transfer) methods.push('transferencia');
  if (config.accepts_card && cardApplies(config.card_applies_to ?? 'both', delivery)) methods.push('tarjeta');
  if (config.accepts_mercadopago && (config.mercadopago_available ?? true)) methods.push('mercadopago');
  return methods.length > 0 ? methods : FALLBACK_METHODS;
}

function cardApplies(appliesTo: string, delivery?: DeliveryMethod): boolean {
  if (appliesTo === 'both' || !delivery) return true;
  return appliesTo === (delivery === 'retiro' ? 'pickup' : 'delivery');
}
