import { useState } from 'react';
import { CartLine } from '@/components/cart/CartLine';
import { TicketIcon } from '@/components/Icons';
import { useCart } from '@/hooks/useCart';
import { lineKeyOf } from '@/utils/cart';
import { formatCurrency } from '@/utils/currency';

export function CartSummary() {
  const {
    items,
    updateQuantity,
    removeItem,
    updateItemModifications,
    splitItem,
    subtotal,
    discountAmount,
    total,
    appliedCoupon,
    applyCoupon,
    removeCoupon,
  } = useCart();
  const [openCustomizationKey, setOpenCustomizationKey] = useState<string | null>(null);
  const [couponInput, setCouponInput] = useState('');
  const [isValidating, setIsValidating] = useState(false);
  const [couponError, setCouponError] = useState<string | null>(null);
  const [couponSuccess, setCouponSuccess] = useState<string | null>(null);

  const handleApplyCoupon = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!couponInput.trim()) return;
    setCouponError(null);
    setCouponSuccess(null);
    setIsValidating(true);
    try {
      const result = await applyCoupon(couponInput.trim());
      if (result.success) {
        setCouponSuccess(result.message);
        setCouponInput('');
      } else {
        setCouponError(result.message);
      }
    } finally {
      setIsValidating(false);
    }
  };

  const handleRemoveCoupon = () => {
    removeCoupon();
    setCouponError(null);
    setCouponSuccess(null);
  };

  return (
    <div className="bg-white rounded-2xl shadow-md p-4 sm:p-5">
      <h2 className="text-lg font-bold text-gray-900 mb-3">Tu carrito</h2>

      {items.length === 0 ? (
        <p className="text-sm text-gray-500">Tu carrito está vacío</p>
      ) : (
        <>
          <ul className="space-y-3.5 divide-y divide-gray-100">
            {items.map((item) => {
              const lineKey = lineKeyOf(item);
              const isPromo = Boolean(item.promotion);
              return (
                <CartLine
                  key={lineKey}
                  item={item}
                  customizationOpen={openCustomizationKey === lineKey}
                  onToggleCustomization={() => setOpenCustomizationKey(openCustomizationKey === lineKey ? null : lineKey)}
                  onQuantityChange={(quantity) => updateQuantity(lineKey, quantity, item.secondary_product?.id, isPromo)}
                  onRemove={() => removeItem(lineKey, item.secondary_product?.id, isPromo)}
                  onModificationsChange={(modifications) => updateItemModifications(lineKey, modifications)}
                  onSplit={() => splitItem?.(lineKey)}
                />
              );
            })}
          </ul>

          {/* Sección Cupón de descuento */}
          <div className="mt-4 pt-3 border-t border-gray-100">
            {appliedCoupon ? (
              <div className="flex items-center justify-between p-2.5 bg-emerald-50 border border-emerald-200 rounded-xl">
                <div className="flex items-center gap-2">
                  <TicketIcon className="w-4 h-4 text-emerald-700 shrink-0" />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-xs text-emerald-900 tracking-wider">
                        {appliedCoupon.code}
                      </span>
                      <span className="text-xs font-semibold text-emerald-700 bg-emerald-100/70 px-1.5 py-0.5 rounded">
                        {appliedCoupon.discount_percentage}% OFF
                      </span>
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleRemoveCoupon}
                  aria-label="Quitar cupón"
                  className="w-6 h-6 flex items-center justify-center rounded-lg text-emerald-800 hover:text-red-600 hover:bg-emerald-100/60 transition text-base font-semibold leading-none"
                >
                  ×
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-gray-700">¿Tenés un cupón?</p>
                <form onSubmit={handleApplyCoupon} className="flex gap-2">
                  <input
                    type="text"
                    value={couponInput}
                    onChange={(e) => {
                      setCouponInput(e.target.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase());
                      setCouponError(null);
                    }}
                    placeholder="Ingresá tu código"
                    className="flex-1 px-3 py-1.5 rounded-lg border border-gray-200 text-xs font-mono font-bold uppercase tracking-wider focus:outline-none focus:ring-1 focus:ring-zinc-900"
                    disabled={isValidating}
                  />
                  <button
                    type="submit"
                    disabled={isValidating || !couponInput.trim()}
                    className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 disabled:opacity-50 text-white text-xs font-bold rounded-lg transition"
                  >
                    {isValidating ? '...' : 'Aplicar'}
                  </button>
                </form>
                {couponError && <p className="text-xs text-red-600 font-medium">{couponError}</p>}
                {couponSuccess && <p className="text-xs text-emerald-600 font-medium">{couponSuccess}</p>}
              </div>
            )}
          </div>

          {/* Desglose de Totales */}
          <div className="space-y-1.5 mt-3 pt-3 border-t border-gray-200">
            {appliedCoupon && (
              <>
                <div className="flex items-center justify-between text-sm text-gray-600">
                  <span>Subtotal</span>
                  <span>{formatCurrency(subtotal)}</span>
                </div>
                <div className="flex items-center justify-between text-sm font-medium text-emerald-600">
                  <span>Descuento ({appliedCoupon.discount_percentage}%)</span>
                  <span>-{formatCurrency(discountAmount)}</span>
                </div>
              </>
            )}
            <div className="flex items-center justify-between pt-1">
              <span className="font-semibold text-gray-900">Total</span>
              <span className="font-bold text-gray-900 text-base">{formatCurrency(total)}</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
