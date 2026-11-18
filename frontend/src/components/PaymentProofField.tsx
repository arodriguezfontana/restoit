import { useRef, useState } from 'react';
import { PROOF_ACCEPT, deletePaymentProof, fetchPaymentProofFile, uploadPaymentProof } from '@/services/orderService';
import type { PaymentProofInfo } from '@/types/order';
import { formatDate, formatTime } from '@/utils/dateTime';
import { getErrorMessage } from '@/utils/errors';
import { proofFileProblem } from '@/utils/paymentProof';

interface PaymentProofFieldProps {
  orderId: number;
  /** Clave del cliente de la web; sin ella se usa la sesión del personal. */
  token?: string | null;
  proof: PaymentProofInfo | null;
  onChange: (proof: PaymentProofInfo | null) => void;
  /** El personal puede ver y quitar el comprobante. */
  staff?: boolean;
  /** Con el pago ya confirmado el comprobante no se reemplaza. */
  locked?: boolean;
}

/** Adjuntar, reemplazar, ver o quitar el comprobante de una transferencia. */
export function PaymentProofField({ orderId, token, proof, onChange, staff = false, locked = false }: PaymentProofFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ type: 'ok' | 'error'; text: string } | null>(null);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    const problem = proofFileProblem(file);
    if (problem) {
      setMessage({ type: 'error', text: problem });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      onChange(await uploadPaymentProof(orderId, file, token ?? undefined));
      setMessage({ type: 'ok', text: 'Comprobante guardado.' });
    } catch (err) {
      setMessage({ type: 'error', text: getErrorMessage(err, 'No se pudo guardar el comprobante.') });
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const handleView = async () => {
    try {
      const url = URL.createObjectURL(await fetchPaymentProofFile(orderId));
      window.open(url, '_blank', 'noopener');
    } catch (err) {
      setMessage({ type: 'error', text: getErrorMessage(err, 'No se pudo abrir el comprobante.') });
    }
  };

  const handleRemove = async () => {
    try {
      await deletePaymentProof(orderId);
      onChange(null);
      setMessage(null);
    } catch (err) {
      setMessage({ type: 'error', text: getErrorMessage(err, 'No se pudo quitar el comprobante.') });
    }
  };

  return (
    <div className="space-y-1.5 text-sm">
      {proof ? (
        <p className="text-gray-700">
          Comprobante adjunto · se elimina el {formatDate(proof.expires_at)} a las {formatTime(proof.expires_at)} hs
        </p>
      ) : (
        <p className="text-gray-500">Todavía no hay comprobante adjunto.</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {!locked && (
          <>
            <input
              ref={inputRef}
              id={`proof-${orderId}`}
              type="file"
              accept={PROOF_ACCEPT}
              className="sr-only"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
            <label
              htmlFor={`proof-${orderId}`}
              className={`cursor-pointer text-xs font-semibold px-3 py-1.5 rounded-lg bg-zinc-900 text-white hover:opacity-90 transition ${busy ? 'opacity-50 pointer-events-none' : ''}`}
            >
              {busy ? 'Subiendo...' : proof ? 'Reemplazar comprobante' : 'Adjuntar comprobante'}
            </label>
          </>
        )}
        {staff && proof && (
          <>
            <button type="button" onClick={handleView} className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-100 transition">
              Ver
            </button>
            {!locked && (
              <button type="button" onClick={handleRemove} className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-red-200 text-red-700 hover:bg-red-50 transition">
                Quitar
              </button>
            )}
          </>
        )}
      </div>
      <p className="text-[11px] text-gray-500">JPG, PNG, WEBP o PDF de hasta 5 MB.</p>
      {message && (
        <p role={message.type === 'error' ? 'alert' : 'status'} className={`text-xs font-semibold ${message.type === 'error' ? 'text-red-700' : 'text-green-700'}`}>
          {message.text}
        </p>
      )}
    </div>
  );
}
