import { useState } from 'react';
import type { FormEvent } from 'react';
import { Row } from '@/components/orderDetail/DetailLayout';
import type { AdminOrder } from '@/types/order';

const ESTIMATE_SOURCE_LABEL = {
  smart: 'Inteligente',
  fixed: 'Regla fija',
  manual: 'Manual',
  default: 'Estándar',
} as const;

interface EstimatedDelayRowProps {
  order: AdminOrder;
  /** Si se indica, el personal puede cargar o modificar la demora a mano. */
  onUpdateDelay?: (orderId: number, minutes: number) => Promise<void>;
}

/** La demora estimada del pedido, de dónde salió y (si se puede) el control para modificarla a mano. */
export function EstimatedDelayRow({ order, onUpdateDelay }: EstimatedDelayRowProps) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);
  const hasDelay = order.estimated_minutes != null;
  const origin = order.estimate_source ? ESTIMATE_SOURCE_LABEL[order.estimate_source] : null;
  const minutes = Number(value);
  const isValid = value.trim() !== '' && Number.isInteger(minutes) && minutes > 0;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!onUpdateDelay || !isValid) return;
    setSaving(true);
    try {
      await onUpdateDelay(order.id, minutes);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  if (!hasDelay && !onUpdateDelay) return null;

  return (
    <>
      <Row label="Demora estimada">
        {editing ? (
          <form onSubmit={(e) => void handleSubmit(e)} className="flex items-center gap-2">
            <input
              type="number"
              min={1}
              step={1}
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              aria-label="Demora estimada en minutos"
              className="w-24 rounded-lg border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-black"
            />
            <button
              type="submit"
              disabled={!isValid || saving}
              className="rounded-lg bg-black px-2.5 py-1 text-xs font-bold text-white disabled:opacity-50"
            >
              Guardar demora
            </button>
            <button type="button" onClick={() => setEditing(false)} className="text-xs font-semibold text-gray-600 underline">
              Cancelar
            </button>
          </form>
        ) : (
          <span className="inline-flex items-center gap-2">
            {hasDelay ? `${order.estimated_minutes} min` : 'Sin demora informada'}
            {onUpdateDelay && (
              <button
                type="button"
                onClick={() => {
                  setValue(hasDelay ? String(order.estimated_minutes) : '');
                  setEditing(true);
                }}
                className="text-xs font-semibold text-gray-700 underline hover:text-gray-900"
              >
                {hasDelay ? 'Modificar demora' : 'Cargar demora'}
              </button>
            )}
          </span>
        )}
      </Row>
      {hasDelay && origin && <Row label="Origen de la demora">{origin}</Row>}
    </>
  );
}
