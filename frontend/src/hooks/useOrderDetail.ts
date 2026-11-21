import { useCallback, useEffect, useState } from 'react';
import { fetchOrderDetail } from '@/services/orderService';
import type { OrderDetail } from '@/types/order';
import { getErrorMessage } from '@/utils/errors';

/**
 * Carga el detalle completo de un pedido (sus productos y su pago).
 */
export function useOrderDetail(orderId: number) {
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    fetchOrderDetail(orderId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setDetail(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(getErrorMessage(err, 'No se pudo cargar el detalle del pedido.'));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [orderId, reloadKey]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    setReloadKey((key) => key + 1);
  }, []);

  /** Refleja en pantalla un cambio ya guardado, sin volver a pedir el detalle. */
  const patchDetail = useCallback((changes: Partial<OrderDetail>) => {
    setDetail((previous) => (previous ? { ...previous, ...changes } : previous));
  }, []);

  return { detail, loading, error, retry, patchDetail };
}
