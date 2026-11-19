import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PaymentMethodsSection } from '@/components/configuracion/PaymentMethodsSection';
import type { PaymentSettings } from '@/hooks/useStoreSettingsForm';

const BASE: PaymentSettings = {
  acceptsCash: true,
  acceptsTransfer: false,
  transferAlias: '',
  transferCbu: '',
  transferHolder: '',
  acceptsCard: false,
  cardAppliesTo: 'both',
  acceptsMercadopago: false,
  proofRetentionHours: '48',
};

function renderSection(payments: Partial<PaymentSettings> = {}, mercadopagoAvailable = true) {
  const setPayments = vi.fn();
  render(<PaymentMethodsSection payments={{ ...BASE, ...payments }} setPayments={setPayments} mercadopagoAvailable={mercadopagoAvailable} />);
  return setPayments;
}

describe('PaymentMethodsSection', () => {
  it('no deja apagar el último medio activo', () => {
    renderSection();

    expect(screen.getByRole('switch', { name: 'Efectivo' })).toBeDisabled();
  });

  it('pide los datos de cobro al activar la transferencia', async () => {
    const setPayments = renderSection();
    await userEvent.setup().click(screen.getByRole('switch', { name: 'Transferencia' }));

    expect(setPayments).toHaveBeenCalledWith(expect.objectContaining({ acceptsTransfer: true }));
  });

  it('muestra los campos de la transferencia y la tarjeta cuando están activas', () => {
    renderSection({ acceptsTransfer: true, acceptsCard: true });

    expect(screen.getByLabelText('Alias')).toBeInTheDocument();
    expect(screen.getByLabelText('Titular')).toBeInTheDocument();
    expect(screen.getByLabelText('Se cobra con tarjeta en')).toBeInTheDocument();
  });

  it('no permite activar MercadoPago sin credenciales', () => {
    renderSection({}, false);

    expect(screen.getByRole('switch', { name: 'MercadoPago' })).toBeDisabled();
    expect(screen.getByText(/No hay credenciales de MercadoPago/)).toBeInTheDocument();
  });
});
