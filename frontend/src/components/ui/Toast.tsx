import { CheckCircleIcon } from '@/components/Icons';

interface ToastProps {
  message: string | null;
  /** Éxito (por defecto) o error. */
  type?: 'success' | 'error';
  /** Si se pasa, el aviso muestra un botón para cerrarlo. */
  onClose?: () => void;
}

/** Aviso en la esquina superior derecha (ver useToast). */
export function Toast({ message, type = 'success', onClose }: ToastProps) {
  if (!message) return null;
  const isError = type === 'error';
  const style = isError ? 'text-red-900 border-red-200/80' : 'text-emerald-900 border-emerald-200/80';
  return (
    <div
      role={isError ? 'alert' : 'status'}
      className={`fixed top-5 right-5 z-50 max-w-sm bg-white border px-4 py-3 rounded-2xl shadow-xl text-sm font-semibold flex items-center gap-2.5 transition animate-in fade-in slide-in-from-top-2 duration-200 ${style}`}
    >
      {isError ? (
        <span aria-hidden className="w-5 h-5 shrink-0 rounded-full bg-red-600 text-white text-xs flex items-center justify-center">
          !
        </span>
      ) : (
        <CheckCircleIcon className="w-5 h-5 text-emerald-600 shrink-0" />
      )}
      <span>{message}</span>
      {onClose && (
        <button type="button" onClick={onClose} aria-label="Cerrar aviso" className="ml-1 text-gray-400 hover:text-gray-700 text-lg leading-none">
          ×
        </button>
      )}
    </div>
  );
}
