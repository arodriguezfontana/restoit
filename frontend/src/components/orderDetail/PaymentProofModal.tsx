import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

interface PaymentProofModalProps {
  imageUrl: string;
  isPdf?: boolean;
  onClose: () => void;
}

/** Visualizador de la imagen o PDF del comprobante de transferencia. */
export function PaymentProofModal({ imageUrl, isPdf = false, onClose }: PaymentProofModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Comprobante de pago"
      className="fixed inset-0 z-[60] bg-black/60 flex items-center justify-center p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl p-5 max-w-lg w-full flex flex-col gap-3 relative max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between pb-2 border-b border-gray-100">
          <h3 className="font-bold text-gray-900 text-sm">Comprobante de pago</h3>
          <button
            ref={closeButtonRef}
            type="button"
            aria-label="Cerrar comprobante"
            onClick={onClose}
            className="w-8 h-8 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 text-xl font-bold flex items-center justify-center transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black"
          >
            ×
          </button>
        </div>
        <div className="flex-1 min-h-0 flex items-center justify-center overflow-auto py-2">
          {isPdf ? (
            <iframe src={imageUrl} title="Comprobante de pago" className="w-full h-[60vh] rounded-lg" />
          ) : (
            <img
              src={imageUrl}
              alt="Comprobante de pago"
              aria-label="Comprobante de pago"
              className="max-w-full max-h-[65vh] object-contain rounded-lg shadow-xs"
            />
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
