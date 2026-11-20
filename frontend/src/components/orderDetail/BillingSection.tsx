import { useState } from 'react';
import { PaymentProofField } from '@/components/PaymentProofField';
import { Row, Section } from '@/components/orderDetail/DetailLayout';
import { PaymentProofModal } from '@/components/orderDetail/PaymentProofModal';
import { fetchPaymentProofFile, updateOrderPayment } from '@/services/orderService';
import { PAYMENT_METHOD_LABEL } from '@/types/order';
import type { AdminOrder, OrderDetail, PaymentMethod, PaymentProofInfo } from '@/types/order';
import { formatCurrency } from '@/utils/currency';
import { formatOrderPaymentMethod } from '@/utils/paymentMethods';
import { isPaymentProofExpired } from '@/utils/paymentProof';

/** El pedido (o la diferencia de un pago parcial) se paga por transferencia. */
function paysByTransfer(paymentMethod?: string | null, balanceMethod?: string | null): boolean {
  return paymentMethod === 'transferencia' || balanceMethod === 'transferencia';
}

function paymentStatusLabel(detail: OrderDetail): string {
  if (detail.is_paid) return detail.payment_method === 'mercadopago' ? 'Abonado' : 'Pagado';
  return (detail.paid_amount ?? 0) > 0 ? 'Pago parcial' : 'Pendiente de pago';
}

function PendingBalanceRows({
  detail,
  balanceMethodOverride,
}: {
  detail: OrderDetail;
  balanceMethodOverride?: PaymentMethod | null;
}) {
  const method = balanceMethodOverride !== undefined ? balanceMethodOverride : detail.balance_payment_method;
  const balanceMethod = method ? ` (${PAYMENT_METHOD_LABEL[method]})` : ' (a definir)';
  return (
    <>
      <Row label="Pagado">{formatCurrency(detail.paid_amount ?? 0)}</Row>
      <Row label="Falta cobrar">
        <span className="font-bold text-sky-800">
          {formatCurrency(detail.pending_amount ?? 0)}
          {balanceMethod}
        </span>
      </Row>
    </>
  );
}

interface PaymentStatusProps {
  detail: OrderDetail;
  markingPaid: boolean;
  onMarkAsPaid?: () => void;
}

function PaymentStatus({ detail, markingPaid, onMarkAsPaid }: PaymentStatusProps) {
  return (
    <Row label="Estado del pago">
      <div className="flex items-center justify-end gap-2">
        <span
          className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${
            detail.is_paid
              ? 'bg-green-100 text-green-800'
              : 'bg-sky-50 text-sky-800 border border-sky-200'
          }`}
        >
          {paymentStatusLabel(detail)}
        </span>
        {!detail.is_paid && onMarkAsPaid && (
          <button
            type="button"
            onClick={onMarkAsPaid}
            disabled={markingPaid}
            className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition disabled:opacity-50 cursor-pointer"
          >
            {markingPaid ? 'Guardando...' : 'Marcar como abonado'}
          </button>
        )}
      </div>
    </Row>
  );
}

interface BillingSectionProps {
  order: AdminOrder;
  detail: OrderDetail | null;
  isDelivery: boolean;
  markingPaid: boolean;
  onMarkAsPaid?: () => void;
}

/** Subtotal, envío, medio y estado de pago, y el total del pedido. */
export function BillingSection({ order, detail, isDelivery, markingPaid, onMarkAsPaid }: BillingSectionProps) {
  const hasPartialPayment = detail && !detail.is_paid && (detail.paid_amount ?? 0) > 0;
  const [proof, setProof] = useState<PaymentProofInfo | null>(detail?.payment_proof ?? null);
  // El comprobante sale del detalle cuando se carga (o se recarga): hasta entonces no hay nada que mostrar.
  const loadedProof = detail?.payment_proof ?? null;
  const [syncedFrom, setSyncedFrom] = useState(loadedProof);
  if (syncedFrom !== loadedProof) {
    setSyncedFrom(loadedProof);
    setProof(loadedProof);
  }

  const isExpired = isPaymentProofExpired(order, proof);
  const hasProof = Boolean(proof) && !isExpired;
  const [viewingProof, setViewingProof] = useState(false);
  const [proofUrl, setProofUrl] = useState<string | null>(null);
  const [changingMethod, setChangingMethod] = useState(false);
  const [savingMethod, setSavingMethod] = useState(false);
  const [methodError, setMethodError] = useState<string | null>(null);

  const [localPaymentMethod, setLocalPaymentMethod] = useState(detail?.payment_method ?? null);
  const [localBalanceMethod, setLocalBalanceMethod] = useState(detail?.balance_payment_method ?? null);

  const syncedPaymentMethod = detail?.payment_method ?? null;
  const syncedBalanceMethod = detail?.balance_payment_method ?? null;
  const [prevSyncedPaymentMethod, setPrevSyncedPaymentMethod] = useState(syncedPaymentMethod);
  const [prevSyncedBalanceMethod, setPrevSyncedBalanceMethod] = useState(syncedBalanceMethod);

  if (prevSyncedPaymentMethod !== syncedPaymentMethod) {
    setPrevSyncedPaymentMethod(syncedPaymentMethod);
    setLocalPaymentMethod(syncedPaymentMethod);
  }
  if (prevSyncedBalanceMethod !== syncedBalanceMethod) {
    setPrevSyncedBalanceMethod(syncedBalanceMethod);
    setLocalBalanceMethod(syncedBalanceMethod);
  }

  const handleChangeMethod = async (newMethod: PaymentMethod) => {
    if (!detail) return;
    setSavingMethod(true);
    setMethodError(null);
    try {
      await updateOrderPayment(order.id, undefined, newMethod);
      if (hasPartialPayment) {
        setLocalBalanceMethod(newMethod);
      } else {
        setLocalPaymentMethod(newMethod);
      }
      setChangingMethod(false);
    } catch {
      setMethodError('No se pudo cambiar el medio de pago.');
    } finally {
      setSavingMethod(false);
    }
  };

  const handleProofChange = (newProof: PaymentProofInfo | null) => {
    setProof(newProof);
    setProofUrl(null);
  };

  const handleViewProof = async () => {
    if (!hasProof || isExpired) return;
    if (!proofUrl) {
      try {
        const blob = await fetchPaymentProofFile(order.id);
        const url = blob && typeof URL.createObjectURL === 'function' ? URL.createObjectURL(blob) : 'blob:comprobante';
        setProofUrl(url);
      } catch {
        setProofUrl('blob:comprobante');
      }
    }
    setViewingProof(true);
  };

  return (
    <Section title="Facturación">
      <dl className="space-y-1.5">
        {detail && (
          <>
            <Row label="Subtotal">{formatCurrency(detail.subtotal)}</Row>
            {isDelivery && (
              <Row label="Costo de envío">
                {detail.shipping_cost > 0 ? formatCurrency(detail.shipping_cost) : 'Sin cargo'}
              </Row>
            )}
            <Row label="Método de pago">
              {changingMethod ? (
                <div className="flex items-center gap-1.5 justify-end flex-wrap">
                  <select
                    aria-label="Seleccionar nuevo medio de pago"
                    defaultValue={
                      hasPartialPayment
                        ? (localBalanceMethod || 'efectivo')
                        : (localPaymentMethod || 'efectivo')
                    }
                    id="change-payment-method-select"
                    disabled={savingMethod}
                    className="text-xs px-2 py-1 rounded-lg border border-gray-300 bg-white"
                  >
                    <option value="efectivo">Efectivo</option>
                    <option value="mercadopago">MercadoPago</option>
                    <option value="transferencia">Transferencia</option>
                    <option value="tarjeta">Tarjeta</option>
                  </select>
                  <button
                    type="button"
                    disabled={savingMethod}
                    onClick={() => {
                      const select = document.getElementById('change-payment-method-select') as HTMLSelectElement;
                      if (select) handleChangeMethod(select.value as PaymentMethod);
                    }}
                    className="text-xs px-2 py-1 rounded-lg bg-zinc-900 text-white font-semibold hover:bg-zinc-800 disabled:opacity-50"
                  >
                    {savingMethod ? 'Guardando...' : 'Guardar'}
                  </button>
                  <button
                    type="button"
                    disabled={savingMethod}
                    onClick={() => setChangingMethod(false)}
                    className="text-xs px-2 py-1 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200"
                  >
                    Cancelar
                  </button>
                </div>
              ) : (
                <div className="flex items-center justify-end gap-2">
                  <span>
                    {formatOrderPaymentMethod({
                      ...detail,
                      payment_method: localPaymentMethod,
                      balance_payment_method: localBalanceMethod,
                    })}
                  </span>
                  {!detail.is_paid && (
                    <button
                      type="button"
                      onClick={() => setChangingMethod(true)}
                      aria-label="Cambiar"
                      title="Cambiar medio de pago"
                      className="p-1 text-gray-500 hover:text-gray-900 rounded-lg hover:bg-gray-100 transition cursor-pointer"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden="true">
                        <path d="m5.433 13.917 1.262-3.155A4 4 0 0 1 7.58 9.42l6.92-6.918a2.121 2.121 0 0 1 3 3l-6.92 6.918c-.383.383-.84.685-1.343.886l-3.154 1.262a.5.5 0 0 1-.65-.65Z" />
                        <path d="M3.5 5.75c0-.69.56-1.25 1.25-1.25H10A.75.75 0 0 0 10 3H4.75A2.75 2.75 0 0 0 2 5.75v9.5A2.75 2.75 0 0 0 4.75 18h9.5A2.75 2.75 0 0 0 17 15.25V10a.75.75 0 0 0-1.5 0v5.25c0 .69-.56 1.25-1.25 1.25h-9.5c-.69 0-1.25-.56-1.25-1.25v-9.5Z" />
                      </svg>
                    </button>
                  )}
                </div>
              )}
            </Row>
            {methodError && (
              <p className="text-xs text-rose-600 text-right">{methodError}</p>
            )}
            {!isExpired && (
              <Row label="Comprobante">
                <div className="flex items-center gap-2">
                  {hasProof && (
                    <button
                      type="button"
                      onClick={handleViewProof}
                      aria-label="Ver miniatura del comprobante"
                      title="Ver comprobante"
                      className="w-7 h-7 rounded-md border border-gray-200 overflow-hidden cursor-pointer hover:ring-2 hover:ring-zinc-900 transition shadow-2xs shrink-0 bg-gray-50 flex items-center justify-center"
                    >
                      {proof?.content_type === 'application/pdf' ? (
                        <span className="text-[9px] font-bold text-red-600">PDF</span>
                      ) : proofUrl ? (
                        <img
                          src={proofUrl}
                          alt="Miniatura del comprobante"
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <span className="text-[9px] text-gray-400">...</span>
                      )}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleViewProof}
                    disabled={!hasProof}
                    className={`text-xs font-semibold px-2.5 py-1 rounded-lg transition ${
                      hasProof
                        ? 'bg-zinc-900 hover:bg-zinc-800 text-white cursor-pointer shadow-xs'
                        : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    }`}
                  >
                    {hasProof ? 'Comprobante' : 'Sin Comprobante'}
                  </button>
                </div>
              </Row>
            )}
            {hasPartialPayment && (
              <PendingBalanceRows detail={detail} balanceMethodOverride={localBalanceMethod} />
            )}
            <PaymentStatus detail={detail} markingPaid={markingPaid} onMarkAsPaid={onMarkAsPaid} />
            {paysByTransfer(localPaymentMethod, localBalanceMethod) && (
              <div className="pt-2">
                <p className="font-semibold text-gray-900 mb-1">Comprobante de la transferencia</p>
                <PaymentProofField
                  orderId={order.id}
                  proof={isExpired ? null : proof}
                  onChange={handleProofChange}
                  staff
                  locked={detail.is_paid && proof !== null}
                />
              </div>
            )}
          </>
        )}
        <div className="flex justify-between items-baseline gap-4 pt-2 mt-1 border-t border-gray-200">
          <dt className="font-bold text-gray-900">{detail?.is_paid ? 'Total (abonado)' : 'Total a pagar'}</dt>
          <dd className="text-xl font-bold text-gray-900">{formatCurrency(order.total_amount)}</dd>
        </div>
      </dl>
      {viewingProof && !isExpired && (
        <PaymentProofModal
          imageUrl={proofUrl || 'blob:comprobante'}
          isPdf={proof?.content_type === 'application/pdf'}
          onClose={() => setViewingProof(false)}
        />
      )}
    </Section>
  );
}
