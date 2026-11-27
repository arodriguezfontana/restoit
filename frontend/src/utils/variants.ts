import type { Product, ProductVariant } from '@/types/order';

/** Si el producto se pide eligiendo una variante (ej. Grande / Chica). */
export function hasVariants(product: Pick<Product, 'variants'>): boolean {
  return (product.variants?.length ?? 0) > 0;
}

/**
 * El producto en la variante elegida: con el precio de esa variante y su nombre en `variant_name`.
 * Así el carrito y el mostrador lo tratan como cualquier producto, y el pedido le manda al servidor la variante.
 */
export function withVariant(product: Product, variant: ProductVariant): Product {
  return { ...product, price: variant.price, variant_name: variant.name };
}

/** El nombre con la variante entre paréntesis (ej. "Muzzarella (Grande)"), salvo que ya la mencione. */
export function withVariantSuffix(name: string, variant?: string | null): string {
  if (!variant || name.toLowerCase().includes(variant.toLowerCase())) return name;
  return `${name} (${variant})`;
}

/** Nombre para mostrar de un producto, con la variante elegida si la tiene. */
export function productDisplayName(product: Pick<Product, 'name' | 'variant_name'>): string {
  return withVariantSuffix(product.name, product.variant_name);
}

/** Variantes que tienen todos los productos (por nombre, sin distinguir mayúsculas), en el orden del primero. */
export function sharedVariants(products: Product[]): ProductVariant[] {
  const [first, ...rest] = products;
  if (!first) return [];
  return (first.variants ?? []).filter((variant) =>
    rest.every((product) =>
      (product.variants ?? []).some((other) => other.name.toLowerCase() === variant.name.toLowerCase())
    )
  );
}

/** La variante del producto con ese nombre (sin distinguir mayúsculas), si la tiene. */
export function variantNamed(product: Product, name: string | undefined): ProductVariant | undefined {
  if (!name) return undefined;
  return product.variants?.find((variant) => variant.name.toLowerCase() === name.toLowerCase());
}

/** Rango de precios para listar el producto: "$14.000 – $16.000" si sus variantes cuestan distinto. */
export function priceRange(product: Pick<Product, 'price' | 'variants'>): { min: number; max: number } {
  const prices = (product.variants ?? []).map((variant) => variant.price);
  if (prices.length === 0) return { min: product.price, max: product.price };
  return { min: Math.min(...prices), max: Math.max(...prices) };
}
