import { useState } from 'react';
import { PaymentProofField } from '@/components/PaymentProofField';
import { Row, Section } from '@/components/orderDetail/DetailLayout';
import { PAYMENT_METHOD_LABEL } from '@/types/order';
import type { AdminOrder, OrderDetail, PaymentProofInfo } from '@/types/order';
import { formatCurrency } from '@/utils/currency';

/** El pedido (o la diferencia de un pago parcial) se paga por transferencia. */
function paysByTransfer(detail: OrderDetail): boolean {
  return detail.payment_method === 'transferencia' || detail.balance_payment_method === 'transferencia';
}

function paymentStatusLabel(detail: OrderDetail): string {
  if (detail.is_paid) return detail.payment_method === 'mercadopago' ? 'Abonado' : 'Pagado';
  return (detail.paid_amount ?? 0) > 0 ? 'Pago parcial' : 'Pendiente de pago';
}

function PendingBalanceRows({ detail }: { detail: OrderDetail }) {
  const balanceMethod = detail.balance_payment_method
    ? ` (${PAYMENT_METHOD_LABEL[detail.balance_payment_method]})`
    : ' (a definir)';
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
          className={`text-xs font-bold px-2 py-0.5 rounded-full ${
            detail.is_paid ? 'bg-green-100 text-green-800' : 'bg-sky-100 text-sky-800'
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
              {detail.payment_method ? PAYMENT_METHOD_LABEL[detail.payment_method] : 'No informado'}
            </Row>
            {hasPartialPayment && <PendingBalanceRows detail={detail} />}
            <PaymentStatus detail={detail} markingPaid={markingPaid} onMarkAsPaid={onMarkAsPaid} />
            {paysByTransfer(detail) && (
              <div className="pt-2">
                <p className="font-semibold text-gray-900 mb-1">Comprobante de la transferencia</p>
                <PaymentProofField
                  orderId={order.id}
                  proof={proof}
                  onChange={setProof}
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
    </Section>
  );
}
