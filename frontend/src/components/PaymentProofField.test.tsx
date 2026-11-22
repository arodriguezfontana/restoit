import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PaymentProofField } from '@/components/PaymentProofField';
import { CopyButton } from '@/components/ui/CopyButton';
import * as orderService from '@/services/orderService';

vi.mock('@/services/orderService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/orderService')>()),
  uploadPaymentProof: vi.fn(),
  deletePaymentProof: vi.fn(),
  fetchPaymentProofFile: vi.fn(),
}));

const service = vi.mocked(orderService);
const PROOF = { content_type: 'image/jpeg', size_bytes: 1000, uploaded_at: '2026-11-18T12:00:00Z', expires_at: '2026-11-20T12:00:00Z' };

beforeEach(() => vi.resetAllMocks());

describe('PaymentProofField', () => {
  it('sube el comprobante con la clave del cliente y avisa que se guardó', async () => {
    service.uploadPaymentProof.mockResolvedValue(PROOF);
    const onChange = vi.fn();
    render(<PaymentProofField orderId={7} token="abc" proof={null} onChange={onChange} />);

    await userEvent.setup().upload(screen.getByLabelText('Adjuntar comprobante'), new File(['x'], 'comp.png', { type: 'image/png' }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(PROOF));
    expect(service.uploadPaymentProof).toHaveBeenCalledWith(7, expect.any(File), 'abc');
    expect(screen.getByText('Comprobante guardado.')).toBeInTheDocument();
  });

  it('rechaza un formato o un peso que el servidor no acepta, sin subirlo', async () => {
    render(<PaymentProofField orderId={7} token="abc" proof={null} onChange={vi.fn()} />);
    const user = userEvent.setup({ applyAccept: false });
    const input = screen.getByLabelText('Adjuntar comprobante');

    await user.upload(input, new File(['x'], 'a.gif', { type: 'image/gif' }));
    expect(screen.getByRole('alert')).toHaveTextContent('JPG, PNG, WEBP o PDF');

    const grande = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    Object.defineProperty(grande, 'size', { value: 6 * 1024 * 1024 });
    await user.upload(input, grande);
    expect(screen.getByRole('alert')).toHaveTextContent('5 MB');
    expect(service.uploadPaymentProof).not.toHaveBeenCalled();
  });

  it('con comprobante ofrece reemplazarlo, y el pago confirmado lo bloquea', () => {
    const { rerender } = render(<PaymentProofField orderId={7} proof={PROOF} onChange={vi.fn()} staff />);
    expect(screen.getByLabelText('Reemplazar comprobante')).toBeInTheDocument();
    expect(screen.getByText(/se elimina el/)).toBeInTheDocument();

    rerender(<PaymentProofField orderId={7} proof={PROOF} onChange={vi.fn()} staff locked />);
    expect(screen.queryByLabelText('Reemplazar comprobante')).not.toBeInTheDocument();
  });

  it('el personal puede quitar el comprobante', async () => {
    service.deletePaymentProof.mockResolvedValue();
    const onChange = vi.fn();
    render(<PaymentProofField orderId={7} proof={PROOF} onChange={onChange} staff />);

    await userEvent.setup().click(screen.getByRole('button', { name: 'Quitar' }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(null));
  });

  it('el personal puede ver el comprobante en un modal tocando el botón Ver o la miniatura', async () => {
    service.fetchPaymentProofFile.mockResolvedValue(new Blob(['img'], { type: 'image/jpeg' }));
    render(<PaymentProofField orderId={7} proof={PROOF} onChange={vi.fn()} staff />);

    expect(screen.getByLabelText('Ver vista previa del comprobante')).toBeInTheDocument();
    const verBtn = screen.getByRole('button', { name: 'Ver' });
    expect(verBtn).toBeInTheDocument();

    await userEvent.setup().click(verBtn);

    expect(await screen.findByRole('dialog', { name: 'Comprobante de pago' })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Cerrar comprobante' }));
    expect(screen.queryByRole('dialog', { name: 'Comprobante de pago' })).not.toBeInTheDocument();
  });
});

describe('CopyButton', () => {
  it('copia el texto y avisa que ya está copiado', async () => {
    const user = userEvent.setup();
    render(<CopyButton text="mi.alias" label="alias" />);

    await user.click(screen.getByRole('button', { name: 'Copiar alias' }));

    expect(await navigator.clipboard.readText()).toBe('mi.alias');
    expect(await screen.findByText('¡Copiado!')).toBeInTheDocument();
  });
});
