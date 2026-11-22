import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CouponsSection } from './CouponsSection';
import * as couponService from '@/services/couponService';
import type { Coupon } from '@/types/coupon';

const MOCK_COUPONS: Coupon[] = [
  {
    id: 1,
    code: 'BIENVENIDA10',
    discount_percentage: 10,
    is_active: true,
    created_at: '2026-11-21T10:00:00Z',
    updated_at: '2026-11-21T10:00:00Z',
  },
  {
    id: 2,
    code: 'INVIERNO20',
    discount_percentage: 20,
    is_active: false,
    created_at: '2026-11-21T10:00:00Z',
    updated_at: '2026-11-21T10:00:00Z',
  },
];

describe('CouponsSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(couponService, 'fetchCoupons').mockResolvedValue(MOCK_COUPONS);
  });

  it('muestra la lista de cupones con sus estados y permite filtrar solo activos', async () => {
    render(<CouponsSection />);

    expect(await screen.findByText('BIENVENIDA10')).toBeInTheDocument();
    expect(screen.getByText('INVIERNO20')).toBeInTheDocument();
    expect(screen.getByText('10% OFF')).toBeInTheDocument();
    expect(screen.getByText('20% OFF')).toBeInTheDocument();
    expect(screen.getByText('Activo')).toBeInTheDocument();
    expect(screen.getByText('Pausado')).toBeInTheDocument();

    // Filtrar solo activos
    const filterCheckbox = screen.getByLabelText('Mostrar solo activos');
    await userEvent.click(filterCheckbox);

    expect(screen.getByText('BIENVENIDA10')).toBeInTheDocument();
    expect(screen.queryByText('INVIERNO20')).not.toBeInTheDocument();
  });

  it('permite crear un nuevo cupón con código y porcentaje de descuento', async () => {
    const newCoupon: Coupon = {
      id: 3,
      code: 'PROMO30',
      discount_percentage: 30,
      is_active: true,
      created_at: '2026-11-21T12:00:00Z',
      updated_at: '2026-11-21T12:00:00Z',
    };
    vi.spyOn(couponService, 'createCoupon').mockResolvedValue(newCoupon);

    render(<CouponsSection />);
    await screen.findByText('BIENVENIDA10');

    const codeInput = screen.getByLabelText('Código del cupón');
    await userEvent.type(codeInput, 'promo30');
    expect(codeInput).toHaveValue('PROMO30');

    // Elegir preset de 30%
    await userEvent.click(screen.getByRole('button', { name: '30%' }));

    const submitBtn = screen.getByRole('button', { name: 'Crear cupón' });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(couponService.createCoupon).toHaveBeenCalledWith({
        code: 'PROMO30',
        discount_percentage: 30,
        is_active: true,
      });
    });

    expect(await screen.findByText('¡Cupón PROMO30 (30% OFF) creado exitosamente!')).toBeInTheDocument();
  });

  it('permite pausar y reactivar un cupón', async () => {
    vi.spyOn(couponService, 'updateCoupon').mockResolvedValue({
      ...MOCK_COUPONS[0],
      is_active: false,
    });

    render(<CouponsSection />);
    await screen.findByText('BIENVENIDA10');

    const pauseBtn = screen.getByRole('button', { name: 'Pausar' });
    await userEvent.click(pauseBtn);

    expect(couponService.updateCoupon).toHaveBeenCalledWith(1, { is_active: false });
    expect(await screen.findByText('Cupón BIENVENIDA10 pausado.')).toBeInTheDocument();
  });

  it('permite eliminar un cupón con confirmación inline', async () => {
    vi.spyOn(couponService, 'deleteCoupon').mockResolvedValue();

    render(<CouponsSection />);
    await screen.findByText('BIENVENIDA10');

    const deleteBtn = screen.getAllByRole('button', { name: 'Eliminar' })[0];
    await userEvent.click(deleteBtn);

    expect(screen.getByText('¿Eliminar?')).toBeInTheDocument();
    const yesBtn = screen.getByRole('button', { name: 'Sí' });
    await userEvent.click(yesBtn);

    expect(couponService.deleteCoupon).toHaveBeenCalledWith(1);
    expect(await screen.findByText('Cupón eliminado.')).toBeInTheDocument();
  });
});
