import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StoreBranding } from '@/components/StoreBranding';
import * as storeConfigService from '@/services/storeConfigService';

vi.mock('@/services/storeConfigService');

beforeEach(() => {
  vi.resetAllMocks();
  document.head.innerHTML = '<link rel="icon" type="image/png" href="/favicon-restoit.png" />';
  document.title = 'RestoIT';
});

describe('StoreBranding', () => {
  it('aplica el nombre y el logo del local a la pestaña', async () => {
    vi.mocked(storeConfigService.fetchStoreConfig).mockResolvedValue({
      id: 1,
      store_name: 'Pizzería Los Troncos',
      logo_url: 'data:image/png;base64,AAAA',
      theme_color: 'black',
    } as never);

    render(<StoreBranding />);

    await waitFor(() => expect(document.title).toBe('Pizzería Los Troncos'));
    expect(document.querySelector('link[rel~="icon"]')?.getAttribute('href')).toBe('data:image/png;base64,AAAA');
  });

  it('si no se puede cargar la configuración deja los valores por defecto', async () => {
    vi.mocked(storeConfigService.fetchStoreConfig).mockRejectedValue(new Error('sin conexión'));

    render(<StoreBranding />);

    await waitFor(() => expect(storeConfigService.fetchStoreConfig).toHaveBeenCalled());
    expect(document.title).toBe('RestoIT');
  });
});
