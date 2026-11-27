import type { RecipeItem } from '@/types/ingredient';
import type { IngredientExtra, PreparationSector, ProductCategory, ProductVariant } from '@/types/order';

/** Producto tal como lo ve el panel: incluye los no disponibles, los sin categoría y su receta. */
export interface AdminProduct {
  id: number;
  name: string;
  description: string | null;
  price: number;
  is_active: boolean;
  dietary_restrictions: string[];
  /** null si se lo quitó de su categoría: mientras tanto no se muestra en el menú. */
  category: ProductCategory | null;
  /** Ruta relativa a la API (ver productImageSrc). */
  image_url: string | null;
  recipe: RecipeItem[];
  allowed_extras?: IngredientExtra[];
  /** Opciones con su precio; `price` es el de la más barata. */
  variants?: ProductVariant[];
}

export interface ProductPayload {
  name: string;
  description: string;
  /** Sin variantes; con variantes el precio sale de ellas. */
  price?: number;
  /** Vacío: el producto tiene un solo precio. */
  variants?: ProductVariant[];
  category_id: number;
  is_active: boolean;
  dietary_restrictions: string[];
  allowed_extra_ids?: number[];
}

/** Qué hacer con la imagen al guardar el formulario del producto. */
export type ImageChange = { type: 'keep' } | { type: 'upload'; file: File } | { type: 'remove' };

export interface CategoryProduct {
  id: number;
  name: string;
  is_active: boolean;
}

export interface AdminCategory {
  id: number;
  name: string;
  sector?: PreparationSector;
  products: CategoryProduct[];
}

export interface CategoryPayload {
  name: string;
  sector?: PreparationSector;
  /** Productos que forman la categoría. Los que estaban en otra se mueven a esta. */
  product_ids: number[];
}

export interface ProductPromotionSummary {
  id: number;
  name: string;
}
