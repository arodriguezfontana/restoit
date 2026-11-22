import { useState } from 'react';
import type { MouseEvent } from 'react';
import { BellIcon } from '@/components/Icons';

/** Evita que los clics en los controles de la tarjeta abran el detalle del pedido. */
const stopPropagation = (event: MouseEvent) => event.stopPropagation();

interface NewOrderBannerProps {
  onSeen?: () => Promise<void>;
}

/** Aviso de pedido nuevo (ya tomado por el local): suena la alerta hasta que el personal lo marca como visto. */
export function NewOrderBanner({ onSeen }: NewOrderBannerProps) {
  const [marking, setMarking] = useState(false);
  return (
    <div
      role="status"
      onClick={stopPropagation}
      className="cursor-default flex items-center justify-between gap-2 rounded-xl bg-emerald-100 border border-emerald-300 px-3 py-2 text-xs font-bold text-emerald-900 animate-pulse"
    >
      <span className="inline-flex items-center gap-1.5">
        <BellIcon className="w-3.5 h-3.5 text-emerald-700 shrink-0" />
        Pedido nuevo
      </span>
      {onSeen && (
        <button
          type="button"
          disabled={marking}
          onClick={async () => {
            setMarking(true);
            try {
              await onSeen();
            } finally {
              setMarking(false);
            }
          }}
          className="shrink-0 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white px-2.5 py-1 transition"
        >
          Visto
        </button>
      )}
    </div>
  );
}
