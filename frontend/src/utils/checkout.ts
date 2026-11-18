import type {
  CartItem,
  CheckoutFormData,
  CheckoutFormErrors,
  WebOrderItemPayload,
} from '@/types/order';
import { PHONE_PATTERN } from '@/utils/customerValidation';

function phoneError(phone: string): string | undefined {
  if (!phone.trim()) return 'Ingresá tu número de teléfono.';
  return PHONE_PATTERN.test(phone.trim()) ? undefined : 'Ingresá un teléfono válido (solo números, espacios, guiones o +).';
}

/** Los errores de los datos del pedido web (vacío si está todo bien). */
export function validateCheckout(form: CheckoutFormData): CheckoutFormErrors {
  const errors: CheckoutFormErrors = {
    name: form.name.trim() ? undefined : 'Ingresá tu nombre.',
    phone: phoneError(form.phone),
    address:
      form.deliveryMethod === 'domicilio' && !form.address.trim() ? 'Ingresá la dirección de entrega.' : undefined,
  };
  return Object.fromEntries(Object.entries(errors).filter(([, message]) => message)) as CheckoutFormErrors;
}

/** Lo que se le manda al servidor de una línea del carrito: solo ids, cantidad y personalizaciones. */
export function toWebOrderItem(item: CartItem): WebOrderItemPayload {
  return {
    quantity: item.quantity,
    ...(item.promotion ? { promotion_id: item.promotion.id } : { product_id: item.product?.id }),
    ...(item.secondary_product?.id ? { secondary_product_id: item.secondary_product.id } : {}),
    ...(item.custom_name ? { custom_name: item.custom_name } : {}),
    ...(item.modifications && item.modifications.length > 0 ? { modifications: item.modifications } : {}),
  };
}
