import { createContext } from 'react';
import type { CartItem, OrderItemModification, Product } from '@/types/order';
import type { Promotion } from '@/types/promotion';

export interface AppliedCoupon {
  code: string;
  discount_percentage: number;
}

export interface CartContextValue {
  items: CartItem[];
  addItem: (product: Product, quantity?: number, secondaryProduct?: Product, customName?: string) => void;
  addPromotion: (promotion: Promotion, quantity?: number) => void;
  removeItem: (idOrLineId: number | string, secondaryProductId?: number, isPromotion?: boolean) => void;
  updateQuantity: (idOrLineId: number | string, quantity: number, secondaryProductId?: number, isPromotion?: boolean) => void;
  updateItemModifications: (lineId: string, modifications: OrderItemModification[]) => void;
  splitItem?: (lineId: string) => void;
  clearCart: () => void;
  subtotal: number;
  discountAmount: number;
  total: number;
  itemCount: number;
  appliedCoupon: AppliedCoupon | null;
  applyCoupon: (code: string) => Promise<{ success: boolean; message: string }>;
  removeCoupon: () => void;
}

export const CartContext = createContext<CartContextValue | undefined>(undefined);
