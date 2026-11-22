import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DelaySettingsSection } from '@/components/configuracion/DelaySettingsSection';
import * as service from '@/services/delayRuleService';
import type { DelaySettings } from '@/types/delayRule';

vi.mock('@/services/delayRuleService');

const settings: DelaySettings = {
  smart_delay_enabled: true,
  pickup_rules: [{ id: 1, delivery_method: 'retiro', min_orders: 0, max_orders: 15, minutes: 20 }],
  delivery_rules: [
    { id: 2, delivery_method: 'domicilio', min_orders: 0, max_orders: 10, minutes: 30 },
    { id: 3, delivery_method: 'domicilio', min_orders: 21, max_orders: null, minutes: 50 },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(service.fetchDelaySettings).mockResolvedValue(settings);
});

describe('DelaySettingsSection', () => {
  it('muestra las reglas de cada método por separado', async () => {
    render(<DelaySettingsSection />);

    const retiro = await screen.findByRole('group', { name: 'Reglas de Retiro' });
    expect(within(retiro).getByText('hasta 15')).toBeInTheDocument();
    const envio = screen.getByRole('group', { name: 'Reglas de Envío' });
    expect(within(envio).getByText('hasta 10')).toBeInTheDocument();
    expect(within(envio).getByText('21 o más')).toBeInTheDocument();
  });

  it('desactiva la demora inteligente', async () => {
    vi.mocked(service.setSmartDelayEnabled).mockResolvedValue({ ...settings, smart_delay_enabled: false });
    render(<DelaySettingsSection />);

    await userEvent.click(await screen.findByRole('switch'));

    expect(service.setSmartDelayEnabled).toHaveBeenCalledWith(false);
    expect(await screen.findByText(/no calcula ni sugiere demoras por historial/)).toBeInTheDocument();
  });

  it('agrega una regla al método de envío', async () => {
    vi.mocked(service.createDelayRule).mockResolvedValue({
      id: 9,
      delivery_method: 'domicilio',
      min_orders: 11,
      max_orders: 20,
      minutes: 40,
    });
    render(<DelaySettingsSection />);
    await screen.findByRole('group', { name: 'Reglas de Envío' });

    await userEvent.clear(screen.getByLabelText('Desde cuántos pedidos (Envío)'));
    await userEvent.type(screen.getByLabelText('Desde cuántos pedidos (Envío)'), '11');
    await userEvent.type(screen.getByLabelText('Hasta cuántos pedidos (Envío)'), '20');
    await userEvent.type(screen.getByLabelText('Minutos de demora (Envío)'), '40');
    await userEvent.click(within(screen.getByRole('form', { name: 'Regla de Envío' })).getByRole('button', { name: 'Agregar regla' }));

    await waitFor(() =>
      expect(service.createDelayRule).toHaveBeenCalledWith('domicilio', { min_orders: 11, max_orders: 20, minutes: 40 })
    );
  });

  it('muestra el error del servidor cuando los rangos se superponen', async () => {
    vi.mocked(service.createDelayRule).mockRejectedValue(new Error('El rango "5 a 12" se superpone con "0 a 10".'));
    render(<DelaySettingsSection />);
    await screen.findByRole('group', { name: 'Reglas de Retiro' });

    await userEvent.type(screen.getByLabelText('Hasta cuántos pedidos (Retiro)'), '12');
    await userEvent.type(screen.getByLabelText('Minutos de demora (Retiro)'), '25');
    await userEvent.click(within(screen.getByRole('form', { name: 'Regla de Retiro' })).getByRole('button', { name: 'Agregar regla' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('se superpone');
  });

  it('valida que los minutos sean mayores a 0 sin llamar al servidor', async () => {
    render(<DelaySettingsSection />);
    await screen.findByRole('group', { name: 'Reglas de Retiro' });

    await userEvent.type(screen.getByLabelText('Hasta cuántos pedidos (Retiro)'), '12');
    await userEvent.type(screen.getByLabelText('Minutos de demora (Retiro)'), '0');
    await userEvent.click(within(screen.getByRole('form', { name: 'Regla de Retiro' })).getByRole('button', { name: 'Agregar regla' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('mayores a 0');
    expect(service.createDelayRule).not.toHaveBeenCalled();
  });

  it('edita y elimina una regla', async () => {
    vi.mocked(service.updateDelayRule).mockResolvedValue(settings.pickup_rules[0]);
    vi.mocked(service.deleteDelayRule).mockResolvedValue();
    render(<DelaySettingsSection />);

    await userEvent.click(await screen.findByRole('button', { name: 'Editar regla hasta 15 de Retiro' }));
    const minutos = screen.getByLabelText('Minutos de demora (Retiro)');
    await userEvent.clear(minutos);
    await userEvent.type(minutos, '25');
    await userEvent.click(screen.getByRole('button', { name: 'Guardar regla' }));
    await waitFor(() =>
      expect(service.updateDelayRule).toHaveBeenCalledWith(1, { min_orders: 0, max_orders: 15, minutes: 25 })
    );

    await userEvent.click(screen.getByRole('button', { name: 'Eliminar regla hasta 15 de Retiro' }));
    await waitFor(() => expect(service.deleteDelayRule).toHaveBeenCalledWith(1));
  });
});
