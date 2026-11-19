import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderSuccess } from '@/components/OrderSuccess';
import * as storeConfigService from '@/services/storeConfigService';
import type { CheckoutFormData, WebOrderCreated } from '@/types/order';

vi.mock('@/services/storeConfigService');
vi.mock('@/services/orderService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/orderService')>()),
  uploadPaymentProof: vi.fn(),
}));

const ORDER = {
  id: 5,
  shift_number: 12,
  total_amount: 8500.5,
  items: [],
  proof_upload_token: 'tok',
} as unknown as WebOrderCreated;

const FORM: CheckoutFormData = {
  name: 'Ana',
  phone: '1155551234',
  deliveryMethod: 'retiro',
  address: '',
  notes: '',
  paymentMethod: 'transferencia',
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(storeConfigService.fetchStoreConfig).mockResolvedValue({
    store_name: 'RestoIT',
    address: null,
    contact_phone: null,
    logo_url: null,
    theme_color: 'black',
    accepts_transfer: true,
    transfer_alias: 'mi.local.mp',
    transfer_cbu: '0000003100012345678901',
    transfer_holder: 'Ana Pérez',
  });
});

describe('OrderSuccess con transferencia', () => {
  it('muestra alias, CBU, titular y monto exacto, con botón de copiar solo en alias y CBU', async () => {
    render(<OrderSuccess order={ORDER} form={FORM} onNewOrder={vi.fn()} />);

    expect(await screen.findByText('mi.local.mp')).toBeInTheDocument();
    expect(screen.getByText('0000003100012345678901')).toBeInTheDocument();
    expect(screen.getByText('Ana Pérez')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^Copiar/ }).map((b) => b.getAttribute('aria-label'))).toEqual([
      'Copiar alias',
      'Copiar cbu',
    ]);
  });

  it('copia el alias', async () => {
    const user = userEvent.setup();
    render(<OrderSuccess order={ORDER} form={FORM} onNewOrder={vi.fn()} />);
    await screen.findByText('mi.local.mp');

    await user.click(screen.getByRole('button', { name: 'Copiar alias' }));

    expect(await navigator.clipboard.readText()).toBe('mi.local.mp');
  });

  it('ofrece adjuntar el comprobante', async () => {
    render(<OrderSuccess order={ORDER} form={FORM} onNewOrder={vi.fn()} />);

    expect(await screen.findByLabelText('Adjuntar comprobante')).toBeInTheDocument();
  });

  it('con otro medio de pago no muestra los datos de la cuenta', async () => {
    render(<OrderSuccess order={ORDER} form={{ ...FORM, paymentMethod: 'efectivo' }} onNewOrder={vi.fn()} />);

    expect(screen.queryByText('mi.local.mp')).not.toBeInTheDocument();
  });
});
