import { useState, useEffect } from 'react';
import type { Coupon } from '@/types/coupon';
import { fetchCoupons, createCoupon, updateCoupon, deleteCoupon } from '@/services/couponService';
import { PanelNote } from '@/components/ui/PanelNote';
import { TicketIcon } from '@/components/Icons';
import { getErrorMessage } from '@/utils/errors';

const DISCOUNT_PRESETS = [5, 10, 15, 20, 25, 30, 50];

export function CouponsSection() {
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterActiveOnly, setFilterActiveOnly] = useState(false);
  const [newCode, setNewCode] = useState('');
  const [newDiscount, setNewDiscount] = useState<number>(15);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCoupons()
      .then((data) => {
        if (!cancelled) setCoupons(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) setActionError(getErrorMessage(err, 'Error al cargar la lista de cupones.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    setActionSuccess(null);

    const cleanCode = newCode.trim().toUpperCase();
    if (!cleanCode) {
      setActionError('Ingresá un código para el cupón.');
      return;
    }
    if (newDiscount < 1 || newDiscount > 100) {
      setActionError('El porcentaje de descuento debe estar entre 1% y 100%.');
      return;
    }

    try {
      setIsSubmitting(true);
      const created = await createCoupon({
        code: cleanCode,
        discount_percentage: newDiscount,
        is_active: true,
      });
      setCoupons((prev) => [created, ...prev]);
      setNewCode('');
      setActionSuccess(`¡Cupón ${created.code} (${created.discount_percentage}% OFF) creado exitosamente!`);
    } catch (err: unknown) {
      setActionError(getErrorMessage(err, 'No se pudo crear el cupón.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggleActive = async (coupon: Coupon) => {
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await updateCoupon(coupon.id, { is_active: !coupon.is_active });
      setCoupons((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setActionSuccess(
        updated.is_active ? `Cupón ${updated.code} reactivado.` : `Cupón ${updated.code} pausado.`
      );
    } catch (err: unknown) {
      setActionError(getErrorMessage(err, 'Error al actualizar el estado del cupón.'));
    }
  };

  const handleDelete = async (couponId: number) => {
    setActionError(null);
    setActionSuccess(null);
    try {
      await deleteCoupon(couponId);
      setCoupons((prev) => prev.filter((c) => c.id !== couponId));
      setDeletingId(null);
      setActionSuccess('Cupón eliminado.');
    } catch (err: unknown) {
      setActionError(getErrorMessage(err, 'Error al eliminar el cupón.'));
      setDeletingId(null);
    }
  };

  const displayedCoupons = filterActiveOnly ? coupons.filter((c) => c.is_active) : coupons;

  return (
    <div className="space-y-6">
      {/* Tarjeta de Crear Cupón */}
      <div className="bg-white p-6 rounded-2xl shadow-xs border border-gray-100 space-y-5">
        <div>
          <div className="flex items-center gap-2">
            <TicketIcon className="w-5 h-5 text-gray-700 shrink-0" />
            <h2 className="text-lg font-bold text-gray-900">Crear nuevo cupón de descuento</h2>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Los cupones aplican un descuento porcentual sobre el total del pedido al momento del checkout online (solo en la web).
          </p>
        </div>

        {actionError && (
          <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-xl text-sm font-medium">
            {actionError}
          </div>
        )}
        {actionSuccess && (
          <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-sm font-medium">
            {actionSuccess}
          </div>
        )}

        <form onSubmit={handleCreate} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="coupon-code-input" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                Código del cupón
              </label>
              <input
                id="coupon-code-input"
                type="text"
                value={newCode}
                onChange={(e) => setNewCode(e.target.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase())}
                placeholder="EJ: PROMOVERANO"
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm font-mono font-bold tracking-wider uppercase focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
                disabled={isSubmitting}
              />
              <span className="text-xs text-gray-400 mt-1 block">Se convertirá automáticamente a mayúsculas.</span>
            </div>

            <div>
              <label htmlFor="coupon-discount-input" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                Porcentaje de descuento
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="coupon-discount-input"
                  type="number"
                  min="1"
                  max="100"
                  value={newDiscount}
                  onChange={(e) => setNewDiscount(Math.max(1, Math.min(100, Number(e.target.value))))}
                  className="w-24 px-3 py-2.5 rounded-xl border border-gray-200 text-sm font-bold text-center focus:outline-none focus:ring-2 focus:ring-zinc-900"
                  disabled={isSubmitting}
                />
                <span className="text-sm font-bold text-gray-700">% OFF</span>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {DISCOUNT_PRESETS.map((pct) => (
                  <button
                    key={pct}
                    type="button"
                    onClick={() => setNewDiscount(pct)}
                    className={`px-2 py-0.5 rounded-lg text-xs font-semibold transition ${
                      newDiscount === pct
                        ? 'bg-zinc-900 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {pct}%
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={isSubmitting || !newCode.trim()}
              className="px-5 py-2.5 bg-zinc-900 hover:bg-zinc-800 disabled:opacity-50 text-white font-bold text-sm rounded-xl transition shadow-xs"
            >
              {isSubmitting ? 'Creando...' : 'Crear cupón'}
            </button>
          </div>
        </form>
      </div>

      {/* Listado de Cupones */}
      <div className="bg-white p-6 rounded-2xl shadow-xs border border-gray-100 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-gray-900">Cupones registrados</h3>
            <p className="text-xs text-gray-500">Gestioná qué cupones están disponibles para tus clientes en la web.</p>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-xs font-semibold text-gray-700 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={filterActiveOnly}
                onChange={(e) => setFilterActiveOnly(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 text-zinc-900 focus:ring-zinc-900"
              />
              Mostrar solo activos
            </label>
          </div>
        </div>

        {loading ? (
          <PanelNote>Cargando cupones...</PanelNote>
        ) : displayedCoupons.length === 0 ? (
          <div className="p-8 text-center border-2 border-dashed border-gray-200 rounded-xl text-gray-400 text-sm">
            {filterActiveOnly ? 'No hay cupones activos actualmente.' : 'No hay cupones creados aún.'}
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {displayedCoupons.map((coupon) => (
              <div
                key={coupon.id}
                className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-base px-3 py-1 bg-gray-100 border border-gray-200 text-gray-900 rounded-lg tracking-wider">
                    {coupon.code}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-emerald-600 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                      {coupon.discount_percentage}% OFF
                    </span>
                    <span
                      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                        coupon.is_active
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {coupon.is_active ? 'Activo' : 'Pausado'}
                    </span>
                  </div>
                </div>

                {deletingId === coupon.id ? (
                  <div className="flex items-center gap-1.5 text-xs self-end sm:self-auto">
                    <span className="text-red-600 font-semibold text-xs">¿Eliminar?</span>
                    <button
                      type="button"
                      onClick={() => handleDelete(coupon.id)}
                      className="px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white rounded-lg font-semibold text-xs transition"
                    >
                      Sí
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeletingId(null)}
                      className="px-2.5 py-1 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg font-semibold text-xs transition"
                    >
                      No
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 self-end sm:self-auto">
                    <button
                      type="button"
                      onClick={() => handleToggleActive(coupon)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                        coupon.is_active
                          ? 'bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200'
                          : 'bg-green-50 text-green-800 hover:bg-green-100 border border-green-200'
                      }`}
                    >
                      {coupon.is_active ? 'Pausar' : 'Reactivar'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeletingId(coupon.id)}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold text-red-600 hover:bg-red-50 border border-red-200 transition"
                    >
                      Eliminar
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
