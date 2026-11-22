import { ProductThumbnail } from '@/components/ProductThumbnail';
import type { AdminProduct } from '@/types/catalog';
import { formatCurrency } from '@/utils/currency';
import { formatQuantity } from '@/utils/ingredients';

interface ProductsTableProps {
  products: AdminProduct[];
  onEdit: (product: AdminProduct) => void;
  onEditRecipe: (product: AdminProduct) => void;
  onDelete: (product: AdminProduct) => void;
}

/** Los productos del catálogo con su categoría, precio y receta. */
export function ProductsTable({ products, onEdit, onEditRecipe, onDelete }: ProductsTableProps) {
  return (
    <div className="overflow-x-auto lg:min-h-0">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 z-10 bg-gray-50 text-[11px] font-bold text-gray-500 uppercase tracking-wider">
          <tr>
            <th className="py-3 px-3 sm:px-4">Producto</th>
            <th className="py-3 px-3 sm:px-4 whitespace-nowrap">Categoría</th>
            <th className="py-3 px-3 sm:px-4 text-right whitespace-nowrap">Precio</th>
            <th className="py-3 px-3 sm:px-4">Receta (por unidad)</th>
            <th className="py-3 px-3 sm:px-4 text-right whitespace-nowrap">Acciones</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {products.map((product) => (
            <tr key={product.id} className="hover:bg-gray-50/50 align-top">
              <td className="py-3 px-3 sm:px-4">
                <div className="flex gap-2.5 min-w-0">
                  <ProductThumbnail product={product} size="sm" />
                  <div className="min-w-0">
                    <p className="font-semibold text-gray-900">
                      {product.name}
                      {!product.is_active && (
                        <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-500">
                          No disponible
                        </span>
                      )}
                    </p>
                    {product.description && (
                      <p className="text-xs text-gray-500 line-clamp-2">{product.description}</p>
                    )}
                    {product.dietary_restrictions && product.dietary_restrictions.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {product.dietary_restrictions.map((restriction) => (
                          <span
                            key={restriction}
                            style={{
                              backgroundColor: '#ffffff',
                              borderColor: 'var(--primary-color, #18181b)',
                              color: 'var(--primary-color, #18181b)',
                            }}
                            className="rounded-full border text-[10px] font-semibold px-2 py-0.5"
                          >
                            {restriction.charAt(0).toUpperCase() + restriction.slice(1)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </td>
              <td className="py-3 px-3 sm:px-4 text-gray-600 whitespace-nowrap">
                {product.category ? (
                  product.category.name
                ) : (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 whitespace-nowrap">
                    Sin categoría
                  </span>
                )}
              </td>
              <td className="py-3 px-3 sm:px-4 text-right font-semibold text-gray-900 whitespace-nowrap">
                {formatCurrency(product.price)}
              </td>
              <td className="py-3 px-3 sm:px-4 text-gray-600">
                {product.recipe.length === 0 ? (
                  <span className="text-gray-400 italic">Sin receta</span>
                ) : (
                  <ul className="space-y-0.5 text-xs">
                    {product.recipe.map((item) => (
                      <li key={item.ingredient_id} className="whitespace-nowrap">
                        {item.ingredient_name}: {formatQuantity(item.quantity, item.unit)}
                      </li>
                    ))}
                  </ul>
                )}
              </td>
              <td className="py-3 px-3 sm:px-4 text-right whitespace-nowrap">
                <div className="inline-flex items-center justify-end gap-1.5">
                  <button
                    type="button"
                    onClick={() => onEdit(product)}
                    aria-label={`Editar ${product.name}`}
                    className="text-xs font-semibold rounded-lg px-2.5 py-1 text-gray-700 hover:bg-gray-200 transition"
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    onClick={() => onEditRecipe(product)}
                    aria-label={`Editar receta de ${product.name}`}
                    className="text-xs font-semibold rounded-lg px-2.5 py-1 text-gray-700 border border-gray-300 hover:bg-gray-100 transition"
                  >
                    Receta
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(product)}
                    aria-label={`Eliminar ${product.name}`}
                    className="text-xs font-semibold rounded-lg px-2.5 py-1 text-red-600 hover:bg-red-50 transition"
                  >
                    Eliminar
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
