import { api } from './api';
import type { Coupon, CouponCreate, CouponUpdate, CouponValidateResponse } from '@/types/coupon';

export async function fetchCoupons(): Promise<Coupon[]> {
  const { data } = await api.get<Coupon[]>('/coupons');
  return data;
}

export async function createCoupon(payload: CouponCreate): Promise<Coupon> {
  const { data } = await api.post<Coupon>('/coupons', payload);
  return data;
}

export async function updateCoupon(id: number, payload: CouponUpdate): Promise<Coupon> {
  const { data } = await api.put<Coupon>(`/coupons/${id}`, payload);
  return data;
}

export async function deleteCoupon(id: number): Promise<void> {
  await api.delete(`/coupons/${id}`);
}

export async function validateCoupon(code: string): Promise<CouponValidateResponse> {
  const { data } = await api.get<CouponValidateResponse>(`/coupons/validate/${encodeURIComponent(code.trim().toUpperCase())}`);
  return data;
}
