import { MAX_QUANTITY_PER_ITEM } from '@/types/order';
import type { Product } from '@/types/order';
import { useCart } from '@/hooks/useCart';
import { ProductThumbnail } from '@/components/ProductThumbnail';
import { formatCurrency } from '@/utils/currency';
import { isPlainLineOf } from '@/utils/cart';
import { productDisplayName, withVariant } from '@/utils/variants';

/** Precio y botón para sumar al carrito un producto (o una de sus variantes, ya con su precio). */
function AddToCartRow({ product, label }: { product: Product; label?: string }) {
  const { items, addItem, updateQuantity } = useCart();
  const cartItem = items.find((item) => isPlainLineOf(item, product.id, undefined, product.variant_name));
  const name = productDisplayName(product);

  return (
    <div className="flex items-center justify-between gap-3">
      <span className="font-semibold text-gray-900">
        {label && <span className="font-medium text-gray-600 mr-2">{label}</span>}
        {formatCurrency(product.price)}
      </span>

      {cartItem ? (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => updateQuantity(cartItem.id ?? product.id, cartItem.quantity - 1)}
            className="w-7 h-7 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-100 transition"
            aria-label={`Quitar una unidad de ${name}`}
          >
            −
          </button>
          <span className="w-5 text-center text-sm font-medium">{cartItem.quantity}</span>
          <button
            type="button"
            onClick={() => updateQuantity(cartItem.id ?? product.id, cartItem.quantity + 1)}
            disabled={cartItem.quantity >= MAX_QUANTITY_PER_ITEM}
            className="w-7 h-7 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-100 transition disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label={`Agregar una unidad de ${name}`}
          >
            +
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => addItem(product)}
          style={{ backgroundColor: 'var(--primary-color, #18181b)' }}
          className="text-white rounded-xl px-4 py-1.5 text-sm font-semibold hover:opacity-90 transition shadow-xs"
          aria-label={label ? `Agregar ${name}` : undefined}
        >
          Agregar
        </button>
      )}
    </div>
  );
}

export function ProductCard({ product }: { product: Product }) {
  const variants = product.variants ?? [];

  return (
    <div className="bg-white rounded-2xl shadow-md p-4 flex gap-4">
      <ProductThumbnail product={product} />
      <div className="flex-1 flex flex-col">
        <h3 className="font-semibold text-gray-900">{product.name}</h3>
        <p className="text-sm text-gray-500 flex-1">{product.description}</p>

        {product.dietary_restrictions.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {product.dietary_restrictions.map((restriction) => (
              <span
                key={restriction}
                style={{
                  backgroundColor: '#ffffff',
                  borderColor: 'var(--primary-color, #18181b)',
                  color: 'var(--primary-color, #18181b)',
                }}
                className="rounded-full border text-xs font-semibold px-2.5 py-0.5 shadow-2xs"
              >
                {restriction.charAt(0).toUpperCase() + restriction.slice(1)}
              </span>
            ))}
          </div>
        )}

        <div className="mt-3 space-y-2">
          {variants.length > 0 ? (
            variants.map((variant) => (
              <AddToCartRow key={variant.name} product={withVariant(product, variant)} label={variant.name} />
            ))
          ) : (
            <AddToCartRow product={product} />
          )}
        </div>
      </div>
    </div>
  );
}
