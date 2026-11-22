import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import type { AdminProduct, ProductPromotionSummary } from '@/types/catalog';
import { getErrorMessage } from '@/utils/errors';

interface ProductDeleteModalProps {
  product: AdminProduct;
  promotions: ProductPromotionSummary[];
  loadingPromotions: boolean;
  onClose: () => void;
  onConfirm: (deletePromotions: boolean) => Promise<void>;
}

export function ProductDeleteModal({
  product,
  promotions,
  loadingPromotions,
  onClose,
  onConfirm,
}: ProductDeleteModalProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasPromotions = promotions.length > 0;

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await onConfirm(hasPromotions);
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo eliminar el producto.'));
      setDeleting(false);
    }
  };

  return (
    <Modal
      title={hasPromotions ? 'Eliminar producto en promoción' : 'Eliminar producto'}
      onClose={onClose}
      closeDisabled={deleting}
      width="md"
    >
      <div className="px-6 py-4 space-y-4">
        {loadingPromotions ? (
          <p className="text-sm text-gray-500">Verificando promociones asociadas...</p>
        ) : hasPromotions ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-700">
              El producto <strong>{product.name}</strong> pertenece a las siguientes promociones:
            </p>
            <ul
              style={{
                borderColor: 'var(--primary-border, #e4e4e7)',
                backgroundColor: 'var(--primary-light, #f4f4f5)',
              }}
              className="border rounded-xl p-3 text-sm space-y-1.5"
            >
              {promotions.map((promo) => (
                <li
                  key={promo.id}
                  className="font-bold flex items-center gap-2"
                  style={{ color: 'var(--primary-text, #18181b)' }}
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: 'var(--primary-color, #18181b)' }}
                  />
                  <span>{promo.name}</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-gray-500">
              Para eliminar el producto se deben eliminar también estas promociones, para evitar errores en la carta.
            </p>
          </div>
        ) : (
          <p className="text-sm text-gray-700">
            ¿Estás seguro de que querés eliminar el producto <strong>{product.name}</strong>? Esta acción no se puede deshacer.
          </p>
        )}

        {error && (
          <div role="alert" className="rounded-xl bg-red-50 text-red-700 px-4 py-3 text-sm">
            {error}
          </div>
        )}
      </div>

      <div className="border-t border-gray-100 px-6 py-4 flex justify-end gap-2 shrink-0">
        <button
          type="button"
          onClick={onClose}
          disabled={deleting}
          className="rounded-xl px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-100 transition disabled:opacity-50"
        >
          Cancelar
        </button>
        <button
          type="button"
          onClick={handleDelete}
          disabled={deleting || loadingPromotions}
          className="text-white bg-red-600 hover:bg-red-700 rounded-xl px-5 py-2 text-sm font-semibold transition disabled:opacity-50"
        >
          {deleting
            ? 'Eliminando...'
            : hasPromotions
              ? 'Eliminar promoción y producto'
              : 'Eliminar'}
        </button>
      </div>
    </Modal>
  );
}
