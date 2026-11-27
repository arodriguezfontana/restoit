import type { ProductVariant } from '@/types/order';

/** Una fila del formulario de variantes: el precio queda como texto mientras se escribe. */
export interface VariantDraft {
  name: string;
  price: string;
}

export const toVariantDrafts = (variants: ProductVariant[] | undefined): VariantDraft[] =>
  (variants ?? []).map((variant) => ({ name: variant.name, price: String(variant.price) }));

/** El problema de las variantes cargadas, o null si están bien (sin variantes también está bien). */
export function variantsError(drafts: VariantDraft[]): string | null {
  if (drafts.some((draft) => !draft.name.trim())) return 'Ingresá el nombre de cada variante.';
  if (drafts.some((draft) => !(Number(draft.price) > 0))) return 'Ingresá un precio mayor a cero para cada variante.';
  const names = drafts.map((draft) => draft.name.trim().toLowerCase());
  if (new Set(names).size !== names.length) return 'Hay dos variantes con el mismo nombre.';
  return null;
}

export const toVariants = (drafts: VariantDraft[]): ProductVariant[] =>
  drafts.map((draft) => ({ name: draft.name.trim(), price: Number(draft.price) }));
