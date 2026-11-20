import { beforeEach, describe, expect, it } from 'vitest';
import { applyStoreBranding } from '@/utils/branding';

const PNG = 'data:image/png;base64,iVBORw0KGgo=';

function favicon(): HTMLLinkElement {
  return document.querySelector<HTMLLinkElement>('link[rel~="icon"]')!;
}

beforeEach(() => {
  document.head.innerHTML = '<link rel="icon" type="image/png" href="/favicon-restoit.png" />';
  document.title = 'RestoIT';
});

describe('applyStoreBranding', () => {
  it('usa el nombre del local como título y su logo como favicon', () => {
    applyStoreBranding({ store_name: 'Pizzería Los Troncos', logo_url: PNG });

    expect(document.title).toBe('Pizzería Los Troncos');
    expect(favicon().getAttribute('href')).toBe(PNG);
    expect(favicon().type).toBe('image/png');
  });

  it('sin logo deja el logo de RestoIT como favicon', () => {
    applyStoreBranding({ store_name: 'Pizzería Los Troncos', logo_url: null });

    expect(document.title).toBe('Pizzería Los Troncos');
    expect(favicon().getAttribute('href')).toBe('/favicon-restoit.png');
    expect(favicon().type).toBe('image/png');
  });

  it('con un logo que es una URL no fuerza el tipo de imagen', () => {
    applyStoreBranding({ store_name: 'Local', logo_url: 'https://ejemplo.com/logo.webp' });

    expect(favicon().getAttribute('href')).toBe('https://ejemplo.com/logo.webp');
    expect(favicon().hasAttribute('type')).toBe(false);
  });

  it('sin configuración o con nombre vacío vuelve al nombre RestoIT', () => {
    applyStoreBranding({ store_name: 'Local', logo_url: PNG });

    applyStoreBranding({ store_name: '   ', logo_url: null });
    expect(document.title).toBe('RestoIT');

    applyStoreBranding(null);
    expect(document.title).toBe('RestoIT');
    expect(favicon().getAttribute('href')).toBe('/favicon-restoit.png');
  });

  it('crea el favicon si la página no tenía uno', () => {
    document.head.innerHTML = '';

    applyStoreBranding({ store_name: 'Local', logo_url: PNG });

    expect(favicon().getAttribute('href')).toBe(PNG);
  });
});
