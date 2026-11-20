import { PAYMENT_METHOD_LABEL } from '@/types/order';
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

export interface OrderPaymentInfo {
  payment_method?: string | null;
  balance_payment_method?: string | null;
  paid_amount?: number | null;
  is_paid?: boolean | null;
}

/** Devuelve la descripción real del medio o medios de pago del pedido (incluyendo pagos parciales/mixtos). */
export function formatOrderPaymentMethod(order?: OrderPaymentInfo | null): string {
  if (!order || !order.payment_method) {
    return 'No informado';
  }
  const methodKey = order.payment_method.toLowerCase();
  let firstMethod: string;
  if (methodKey.includes('transferencia')) {
    firstMethod = 'Transferencia';
  } else if (methodKey.includes('tarjeta')) {
    firstMethod = 'Tarjeta';
  } else {
    firstMethod = PAYMENT_METHOD_LABEL[methodKey as PaymentMethod] || order.payment_method;
  }

  if (
    order.balance_payment_method &&
    order.balance_payment_method.toLowerCase() !== methodKey &&
    (order.paid_amount ?? 0) > 0
  ) {
    const balKey = order.balance_payment_method.toLowerCase();
    let secondMethod: string;
    if (balKey.includes('transferencia')) {
      secondMethod = 'Transferencia';
    } else if (balKey.includes('tarjeta')) {
      secondMethod = 'Tarjeta';
    } else {
      secondMethod = PAYMENT_METHOD_LABEL[balKey as PaymentMethod] || order.balance_payment_method;
    }
    return `${firstMethod} + ${secondMethod}`;
  }

  return firstMethod;
}
