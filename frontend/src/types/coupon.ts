export interface Coupon {
  id: number;
  code: string;
  discount_percentage: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CouponCreate {
  code: string;
  discount_percentage: number;
  is_active?: boolean;
}

export interface CouponUpdate {
  code?: string;
  discount_percentage?: number;
  is_active?: boolean;
}

export interface CouponValidateResponse {
  valid: boolean;
  code: string;
  discount_percentage: number;
  message?: string | null;
}
