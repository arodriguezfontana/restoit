import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CartSummary } from './CartSummary';
import { CartProvider } from '@/context/CartContext';
import { useCart } from '@/hooks/useCart';
import * as couponService from '@/services/couponService';
import type { Product } from '@/types/order';

const mockProduct: Product = {
  id: 1,
  name: 'Pizza Especial',
  description: 'Con jamón y morrones',
  price: 10000,
  category: { id: 1, name: 'Pizzas' },
  dietary_restrictions: [],
  image_url: null,
};

function TestWrapper() {
  const { addItem } = useCart();
  return (
    <div>
      <button type="button" onClick={() => addItem(mockProduct, 1)}>
        Agregar Producto
      </button>
      <CartSummary />
    </div>
  );
}

describe('CartSummary con Cupones', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('permite aplicar un cupón válido y descuenta el porcentaje del total', async () => {
    vi.spyOn(couponService, 'validateCoupon').mockResolvedValue({
      valid: true,
      code: 'VERANO20',
      discount_percentage: 20,
      message: null,
    });

    render(
      <CartProvider>
        <TestWrapper />
      </CartProvider>
    );

    // Agregar producto al carrito
    await userEvent.click(screen.getByRole('button', { name: 'Agregar Producto' }));

    // Ver total inicial: $10.000
    expect(screen.getByText('Total')).toBeInTheDocument();
    expect(screen.getAllByText(/10\.000/).length).toBeGreaterThan(0);

    // Ver pregunta "¿Tenés un cupón?"
    expect(screen.getByText('¿Tenés un cupón?')).toBeInTheDocument();
    const couponInput = screen.getByPlaceholderText('Ingresá tu código');
    await userEvent.type(couponInput, 'verano20');
    expect(couponInput).toHaveValue('VERANO20');

    // Aplicar
    await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }));

    // Total con 20% OFF en $10.000 = $8.000
    await waitFor(() => {
      expect(screen.getByText('VERANO20')).toBeInTheDocument();
      expect(screen.getByText('20% OFF')).toBeInTheDocument();
      expect(screen.getByText('Subtotal')).toBeInTheDocument();
      expect(screen.getByText('Descuento (20%)')).toBeInTheDocument();
      expect(screen.getByText(/-.*2\.000/)).toBeInTheDocument();
      expect(screen.getAllByText(/8\.000/).length).toBeGreaterThan(0);
    });

    // Permite quitar el cupón con la 'x'
    const removeBtn = screen.getByRole('button', { name: 'Quitar cupón' });
    await userEvent.click(removeBtn);

    // Vuelve al total original
    expect(screen.queryByText('VERANO20')).not.toBeInTheDocument();
    expect(screen.getAllByText(/10\.000/).length).toBeGreaterThan(0);
  });

  it('muestra mensaje de error si el cupón es inválido', async () => {
    vi.spyOn(couponService, 'validateCoupon').mockResolvedValue({
      valid: false,
      code: 'INVALIDO',
      discount_percentage: 0,
      message: 'El cupón no es válido o ha expirado.',
    });

    render(
      <CartProvider>
        <TestWrapper />
      </CartProvider>
    );

    await userEvent.click(screen.getByRole('button', { name: 'Agregar Producto' }));

    const couponInput = screen.getByPlaceholderText('Ingresá tu código');
    await userEvent.type(couponInput, 'invalido');
    await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }));

    expect(await screen.findByText('El cupón no es válido o ha expirado.')).toBeInTheDocument();
    expect(screen.getAllByText(/10\.000/).length).toBeGreaterThan(0);
  });
});
