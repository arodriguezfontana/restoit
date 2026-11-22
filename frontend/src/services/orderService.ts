import { api } from './api';
import type {
  AdminOrder,
  CounterOrderPayload,
  DeliveryTrip,
  OrderDetail,
  OrderStatus,
  PaymentMethod,
  PaymentProofInfo,
  PreparationSector,
  WebOrderCreated,
  WebOrderPayload,
} from '@/types/order';
import type { PrintResult } from '@/types/printer';

export interface FetchOrdersParams {
  dateFrom?: Date;
  dateTo?: Date;
  status?: OrderStatus[];
  sector?: PreparationSector;
}

export async function fetchOrders(params: FetchOrdersParams = {}): Promise<AdminOrder[]> {
  const { data } = await api.get<AdminOrder[]>('/orders', {
    params: {
      date_from: params.dateFrom?.toISOString(),
      date_to: params.dateTo?.toISOString(),
      status: params.status,
      sector: params.sector,
    },
    // FastAPI's `status: list[str] = Query(None)` binds repeated `status=a&status=b`,
    // not axios's default bracketed `status[]=a&status[]=b`.
    paramsSerializer: { indexes: null },
  });
  return data;
}

export async function fetchOrderDetail(orderId: number, signal?: AbortSignal): Promise<OrderDetail> {
  const { data } = await api.get<OrderDetail>(`/orders/${orderId}`, { signal });
  return data;
}

export async function updateOrderStatus(orderId: number, status: OrderStatus): Promise<AdminOrder> {
  const { data } = await api.patch<AdminOrder>(`/orders/${orderId}/status`, { status });
  return data;
}

/** El personal carga o modifica a mano la demora estimada de un pedido. */
export async function updateOrderDelay(orderId: number, estimatedMinutes: number): Promise<AdminOrder> {
  const { data } = await api.patch<AdminOrder>(`/orders/${orderId}/delay`, { estimated_minutes: estimatedMinutes });
  return data;
}

/** El personal vio el pedido nuevo: se apaga su alerta sonora. */
export async function markOrderSeen(orderId: number): Promise<AdminOrder> {
  const { data } = await api.post<AdminOrder>(`/orders/${orderId}/seen`);
  return data;
}

/**
 * Inicia el viaje de un repartidor: el servidor calcula una sola ruta con todos sus pedidos armados y avisa a cada
 * cliente su llegada estimada. Sin `orderIds` salen todos los pedidos que tiene armados.
 */
export async function dispatchTrip(deliveryDriverId: number, orderIds?: number[]): Promise<DeliveryTrip> {
  const { data } = await api.post<DeliveryTrip>('/orders/trips/dispatch', {
    delivery_driver_id: deliveryDriverId,
    ...(orderIds ? { order_ids: orderIds } : {}),
  });
  return data;
}

/** Vuelve a imprimir la comanda de un pedido. No lanza si la impresora falla: informa el resultado. */
export async function reprintOrder(orderId: number): Promise<PrintResult> {
  const { data } = await api.post<PrintResult>(`/orders/${orderId}/print`);
  return data;
}

/** Pedido presencial cargado por el personal desde el panel (entra directamente confirmado). */
export async function createCounterOrder(payload: CounterOrderPayload): Promise<WebOrderCreated> {
  const { data } = await api.post<WebOrderCreated>('/orders/counter', payload);
  return data;
}

export async function createWebOrder(payload: WebOrderPayload): Promise<WebOrderCreated> {
  const { data } = await api.post<WebOrderCreated>('/orders/web', payload);
  return data;
}

/** Asigna o desasigna un repartidor a un pedido con envío a domicilio. */
export async function assignDeliveryDriver(
  orderId: number,
  deliveryDriverId: number | null
): Promise<AdminOrder> {
  const { data } = await api.patch<AdminOrder>(`/orders/${orderId}/delivery-driver`, {
    delivery_driver_id: deliveryDriverId,
  });
  return data;
}

/** Actualiza manualmente el estado de cobro de un pedido (Abonado) o su medio de pago. */
export async function updateOrderPayment(
  orderId: number,
  isPaid?: boolean,
  paymentMethod?: PaymentMethod
): Promise<AdminOrder> {
  const payload: { is_paid?: boolean; payment_method?: PaymentMethod } = {};
  if (isPaid !== undefined) payload.is_paid = isPaid;
  if (paymentMethod !== undefined) payload.payment_method = paymentMethod;
  const { data } = await api.patch<AdminOrder>(`/orders/${orderId}/payment`, payload);
  return data;
}

/** Cocina vio los productos que el cliente agregó al pedido: apaga la alerta del tablero. */
export async function acknowledgeKitchenUpdate(orderId: number): Promise<AdminOrder> {
  const { data } = await api.post<AdminOrder>(`/orders/${orderId}/kitchen-update/ack`);
  return data;
}

/** Marca o desmarca un ítem individual como preparado. */
export async function updateOrderItemPrepared(
  orderId: number,
  itemId: number,
  isPrepared: boolean
): Promise<AdminOrder> {
  const { data } = await api.patch<AdminOrder>(`/orders/${orderId}/items/${itemId}/prepared`, {
    is_prepared: isPrepared,
  });
  return data;
}

/** Marca o desmarca todos los ítems de un sector como preparados. */
export async function updateOrderSectorPrepared(
  orderId: number,
  sector: string,
  isPrepared: boolean
): Promise<AdminOrder> {
  const { data } = await api.patch<AdminOrder>(`/orders/${orderId}/sectors/${sector}/prepared`, {
    is_prepared: isPrepared,
  });
  return data;
}


/** Formatos y peso máximo del comprobante de una transferencia (los mismos que valida el servidor). */
export const PROOF_ACCEPT = 'image/jpeg,image/png,image/webp,application/pdf';
export const PROOF_MAX_BYTES = 5 * 1024 * 1024;

/**
 * Adjunta (o reemplaza) el comprobante de una transferencia. El cliente de la web lo hace con la clave que recibió al
 * hacer el pedido; el personal, con su sesión.
 */
export async function uploadPaymentProof(orderId: number, file: File, token?: string): Promise<PaymentProofInfo | null> {
  const config = { headers: { 'Content-Type': file.type || 'application/octet-stream' }, timeout: 30000 };
  const { data } = token
    ? await api.put<AdminOrder>(`/orders/web/${orderId}/payment-proof`, file, { ...config, params: { token } })
    : await api.put<AdminOrder>(`/orders/${orderId}/payment-proof`, file, config);
  return data.payment_proof ?? null;
}

/** El archivo del comprobante (solo el personal). */
export async function fetchPaymentProofFile(orderId: number): Promise<Blob> {
  const { data } = await api.get<Blob>(`/orders/${orderId}/payment-proof`, { responseType: 'blob' });
  return data;
}

export async function deletePaymentProof(orderId: number): Promise<void> {
  await api.delete(`/orders/${orderId}/payment-proof`);
}
