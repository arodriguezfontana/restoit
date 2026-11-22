import { useEffect, useRef, useState } from 'react';
import { PaymentProofModal } from '@/components/orderDetail/PaymentProofModal';
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
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (!proof) return;
    let active = true;
    try {
      const res = fetchPaymentProofFile(orderId);
      if (res && typeof res.then === 'function') {
        res
          .then((blob) => {
            if (active && blob) {
              setPreviewUrl(typeof URL.createObjectURL === 'function' ? URL.createObjectURL(blob) : 'blob:comprobante');
            }
          })
          .catch(() => {
            if (active) setPreviewUrl('blob:comprobante');
          });
      }
    } catch {
      // ignore
    }
    return () => {
      active = false;
    };
  }, [orderId, proof, token]);

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
    let url = previewUrl;
    if (!url) {
      try {
        const res = fetchPaymentProofFile(orderId);
        const blob = res && typeof (res as Promise<Blob>).then === 'function' ? await res : res;
        url = blob && typeof URL.createObjectURL === 'function' ? URL.createObjectURL(blob as Blob) : 'blob:comprobante';
        setPreviewUrl(url);
      } catch (err) {
        setMessage({ type: 'error', text: getErrorMessage(err, 'No se pudo abrir el comprobante.') });
        return;
      }
    }
    setModalOpen(true);
  };

  const handleRemove = async () => {
    try {
      await deletePaymentProof(orderId);
      onChange(null);
      setMessage(null);
      setPreviewUrl(null);
    } catch (err) {
      setMessage({ type: 'error', text: getErrorMessage(err, 'No se pudo quitar el comprobante.') });
    }
  };

  return (
    <div className="space-y-2 text-sm">
      {proof ? (
        <div className="flex items-center gap-3 py-1">
          {/* Pequeña vista previa del comprobante */}
          <button
            type="button"
            onClick={handleView}
            aria-label="Ver vista previa del comprobante"
            title="Ver comprobante ampliado"
            className="w-14 h-14 rounded-xl border border-gray-200 overflow-hidden cursor-pointer hover:ring-2 hover:ring-emerald-600 transition shadow-xs shrink-0 bg-gray-50 flex items-center justify-center relative group"
          >
            {proof.content_type === 'application/pdf' ? (
              <span className="text-[11px] font-bold text-red-600 uppercase">PDF</span>
            ) : previewUrl ? (
              <img
                src={previewUrl}
                alt="Vista previa del comprobante"
                className="w-full h-full object-cover group-hover:scale-105 transition"
              />
            ) : (
              <span className="text-[10px] text-gray-400">...</span>
            )}
            <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition flex items-center justify-center text-white">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden="true">
                <path d="M10 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />
                <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 0 1 0-1.186A10.004 10.004 0 0 1 10 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0 1 10 17c-4.257 0-7.893-2.66-9.336-6.41ZM14 10a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z" clipRule="evenodd" />
              </svg>
            </div>
          </button>
          <div className="min-w-0">
            <p className="text-xs text-gray-700">
              Comprobante adjunto · se elimina el {formatDate(proof.expires_at)} a las {formatTime(proof.expires_at)} hs
            </p>
          </div>
        </div>
      ) : (
        <p className="text-gray-500 text-xs">Todavía no hay comprobante adjunto.</p>
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
              className={`cursor-pointer text-xs font-semibold px-3 py-1.5 rounded-lg transition ${
                proof
                  ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs'
                  : 'bg-zinc-900 hover:opacity-90 text-white'
              } ${busy ? 'opacity-50 pointer-events-none' : ''}`}
            >
              {busy ? 'Subiendo...' : proof ? 'Reemplazar comprobante' : 'Adjuntar comprobante'}
            </label>
          </>
        )}
        {staff && proof && (
          <>
            <button
              type="button"
              onClick={handleView}
              aria-label="Ver"
              title="Ver comprobante"
              className="p-1.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-100 hover:text-gray-900 transition flex items-center justify-center cursor-pointer shadow-xs"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden="true">
                <path d="M10 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />
                <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 0 1 0-1.186A10.004 10.004 0 0 1 10 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0 1 10 17c-4.257 0-7.893-2.66-9.336-6.41ZM14 10a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z" clipRule="evenodd" />
              </svg>
            </button>
            {!locked && (
              <button
                type="button"
                onClick={handleRemove}
                aria-label="Quitar"
                title="Quitar comprobante"
                className="p-1.5 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700 transition flex items-center justify-center cursor-pointer shadow-xs"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden="true">
                  <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.52.149.023a.75.75 0 0 0 .23-1.482A41.03 41.03 0 0 0 14 4.193V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4ZM8.58 7.72a.75.75 0 0 0-1.5.06l.3 7.5a.75.75 0 1 0 1.5-.06l-.3-7.5Zm4.34.06a.75.75 0 1 0-1.5-.06l-.3 7.5a.75.75 0 1 0 1.5.06l.3-7.5Z" clipRule="evenodd" />
                </svg>
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

      {modalOpen && (
        <PaymentProofModal
          imageUrl={previewUrl || 'blob:comprobante'}
          isPdf={proof?.content_type === 'application/pdf'}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}
