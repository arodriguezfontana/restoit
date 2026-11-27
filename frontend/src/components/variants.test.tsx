import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PizzaMitadYMitadModal } from '@/components/PizzaMitadYMitadModal';
import { ProductCard } from '@/components/ProductCard';
import { TomarPedidoView } from '@/components/TomarPedidoView';
import { CartProvider } from '@/context/CartContext';
import { useCart } from '@/hooks/useCart';
import * as clientService from '@/services/clientService';
import * as menuService from '@/services/menuService';
import * as promotionService from '@/services/promotionService';
import * as storeConfigService from '@/services/storeConfigService';
import { COCA, makeProduct } from '@/test/utils';
import { toWebOrderItem } from '@/utils/checkout';
import { formatPizzaHalfName } from '@/utils/pizzaHalf';
import { priceRange, productDisplayName, sharedVariants, withVariant } from '@/utils/variants';
import { variantsError } from '@/utils/variantDrafts';

vi.mock('@/services/menuService');
vi.mock('@/services/orderService');
vi.mock('@/services/clientService');
vi.mock('@/services/promotionService');
vi.mock('@/services/storeConfigService');

const MUZZA = makeProduct({
  id: 10,
  name: 'Muzzarella',
  price: 14000,
  variants: [
    { name: 'Grande', price: 16000 },
    { name: 'Chica', price: 14000 },
  ],
});
const NAPO = makeProduct({
  id: 11,
  name: 'Napolitana',
  price: 17000,
  variants: [
    { name: 'Grande', price: 19000 },
    { name: 'Chica', price: 17000 },
  ],
});
const PIZZANEZA = makeProduct({
  id: 12,
  name: 'Pizzaneza Napolitana',
  price: 36000,
  variants: [
    { name: 'Carne', price: 38000 },
    { name: 'Pollo', price: 36000 },
  ],
});

function CartInspector() {
  const { items, total } = useCart();
  return (
    <div>
      <span data-testid="total">{total}</span>
      <ul aria-label="carrito">
        {items.map((item) => (
          <li key={item.id}>{JSON.stringify(toWebOrderItem(item))}</li>
        ))}
      </ul>
    </div>
  );
}

const cartPayload = () =>
  within(screen.getByRole('list', { name: 'carrito' }))
    .queryAllByRole('listitem')
    .map((li) => JSON.parse(li.textContent ?? '{}'));

describe('utilidades de variantes', () => {
  it('el producto en una variante toma su precio y la muestra en el nombre', () => {
    const grande = withVariant(MUZZA, MUZZA.variants![0]);

    expect(grande.price).toBe(16000);
    expect(productDisplayName(grande)).toBe('Muzzarella (Grande)');
    expect(productDisplayName(MUZZA)).toBe('Muzzarella');
  });

  it('calcula el rango de precios y las variantes en común', () => {
    expect(priceRange(MUZZA)).toEqual({ min: 14000, max: 16000 });
    expect(priceRange(COCA)).toEqual({ min: 2500, max: 2500 });
    expect(sharedVariants([MUZZA, NAPO]).map((v) => v.name)).toEqual(['Grande', 'Chica']);
    expect(sharedVariants([MUZZA, PIZZANEZA])).toEqual([]);
  });

  it('valida las variantes del formulario', () => {
    expect(variantsError([])).toBeNull();
    expect(variantsError([{ name: 'Grande', price: '100' }])).toBeNull();
    expect(variantsError([{ name: '', price: '100' }])).toMatch(/nombre/);
    expect(variantsError([{ name: 'Grande', price: '0' }])).toMatch(/precio/);
    expect(variantsError([{ name: 'Grande', price: '1' }, { name: 'grande', price: '2' }])).toMatch(/mismo nombre/);
  });

  it('el nombre de la mitad y mitad lleva el tamaño o, si es otra variante, la pone al final', () => {
    expect(formatPizzaHalfName('Muzzarella', 'Napolitana', 'Chica')).toBe('Pizza Chica [1/2 Muzzarella | 1/2 Napolitana]');
    expect(formatPizzaHalfName('A', 'B', 'Pollo')).toBe('Pizza [1/2 A | 1/2 B] (Pollo)');
  });
});

describe('menú web con variantes', () => {
  it('ofrece cada variante con su precio y la manda en el pedido', async () => {
    const user = userEvent.setup();
    render(
      <CartProvider>
        <ProductCard product={MUZZA} />
        <CartInspector />
      </CartProvider>
    );

    expect(screen.getByText('Grande')).toBeInTheDocument();
    expect(screen.getByText('Chica')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Agregar Muzzarella (Grande)' }));
    await user.click(screen.getByRole('button', { name: 'Agregar una unidad de Muzzarella (Grande)' }));
    await user.click(screen.getByRole('button', { name: 'Agregar Muzzarella (Chica)' }));

    expect(screen.getByTestId('total')).toHaveTextContent(String(2 * 16000 + 14000));
    expect(cartPayload()).toEqual([
      { quantity: 2, product_id: 10, variant: 'Grande' },
      { quantity: 1, product_id: 10, variant: 'Chica' },
    ]);
  });

  it('un producto sin variantes se agrega como siempre', async () => {
    const user = userEvent.setup();
    render(
      <CartProvider>
        <ProductCard product={COCA} />
        <CartInspector />
      </CartProvider>
    );

    await user.click(screen.getByRole('button', { name: 'Agregar' }));

    expect(cartPayload()).toEqual([{ quantity: 1, product_id: COCA.id }]);
  });

  it('la mitad y mitad se arma en el tamaño elegido', async () => {
    const user = userEvent.setup();
    render(
      <CartProvider>
        <PizzaMitadYMitadModal pizzas={[MUZZA, NAPO]} onClose={vi.fn()} />
        <CartInspector />
      </CartProvider>
    );

    await user.click(screen.getByRole('radio', { name: 'Chica' }));
    expect(screen.getByText('Pizza Chica [1/2 Muzzarella | 1/2 Napolitana]')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Agregar al carrito' }));

    expect(screen.getByTestId('total')).toHaveTextContent('17000');
    expect(cartPayload()).toEqual([
      {
        quantity: 1,
        product_id: 10,
        secondary_product_id: 11,
        custom_name: 'Pizza Chica [1/2 Muzzarella | 1/2 Napolitana]',
        variant: 'Chica',
      },
    ]);
  });

  it('no deja combinar gustos que no vienen en el mismo tamaño', async () => {
    const user = userEvent.setup();
    render(
      <CartProvider>
        <PizzaMitadYMitadModal pizzas={[MUZZA, PIZZANEZA]} onClose={vi.fn()} />
        <CartInspector />
      </CartProvider>
    );

    expect(screen.getByRole('alert')).toHaveTextContent('no vienen en el mismo tamaño');
    expect(screen.getByRole('button', { name: 'Agregar al carrito' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Agregar al carrito' }));
    expect(cartPayload()).toEqual([]);
  });
});

describe('mostrador con variantes', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(storeConfigService).fetchStoreConfig.mockResolvedValue({
      store_name: 'La Isla',
      address: null,
      contact_phone: null,
      logo_url: null,
      theme_color: 'black',
      accepts_transfer: true,
      accepts_card: true,
      accepts_mercadopago: true,
      mercadopago_available: true,
    });
    vi.mocked(menuService).fetchMenuProducts.mockResolvedValue([MUZZA, COCA]);
    vi.mocked(clientService).lookupClientByPhone.mockResolvedValue(null);
    vi.mocked(promotionService).fetchAvailablePromotions.mockResolvedValue([]);
  });

  it('muestra una ficha por variante y las suma por separado', async () => {
    render(<TomarPedidoView />);
    const user = userEvent.setup();
    const catalog = (await screen.findByRole('heading', { name: 'Productos' })).closest('section') as HTMLElement;
    const grande = await within(catalog).findByRole('button', { name: /Muzzarella\s*Grande/ });
    const chica = within(catalog).getByRole('button', { name: /Muzzarella\s*Chica/ });

    await user.click(grande);
    await user.click(grande);
    await user.click(chica);

    const summary = screen.getByRole('heading', { name: 'Resumen del pedido' }).closest('section') as HTMLElement;
    expect(within(summary).getByText('Unidades: 3 · Productos: 2')).toBeInTheDocument();
    expect(within(summary).getByText('Muzzarella (Grande)')).toBeInTheDocument();
    expect(within(summary).getByText('Muzzarella (Chica)')).toBeInTheDocument();
  });
});
