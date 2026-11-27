import type { AdminProduct } from '@/types/catalog';

export interface PromotionLine {
  product_id: number;
  quantity: number;
  /** Variante incluida de un producto que las tiene (ej. Grande). */
  variant_name?: string | null;
}

/** Lo que se puede sumar a la promo: cada producto o, si tiene variantes, cada una de ellas. */
export interface PromotionOption {
  key: string;
  productId: number;
  variantName: string | null;
  label: string;
  price: number;
}

export function optionsOf(products: AdminProduct[]): PromotionOption[] {
  return products.flatMap((product): PromotionOption[] =>
    product.variants && product.variants.length > 0
      ? product.variants.map((variant) => ({
          key: `${product.id}|${variant.name}`,
          productId: product.id,
          variantName: variant.name,
          label: `${product.name} (${variant.name})`,
          price: variant.price,
        }))
      : [{ key: String(product.id), productId: product.id, variantName: null, label: product.name, price: product.price }]
  );
}

/** Precio de una unidad del producto de la línea (en su variante, si tiene). */
export function linePrice(line: PromotionLine, product: AdminProduct | undefined): number {
  if (!product) return 0;
  const variant = product.variants?.find((v) => v.name.toLowerCase() === (line.variant_name ?? '').toLowerCase());
  return variant ? variant.price : product.price;
}
