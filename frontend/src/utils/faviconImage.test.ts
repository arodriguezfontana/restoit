import { describe, expect, it } from 'vitest';
import { addWhiteOutline, cutOutBackground } from '@/utils/faviconImage';
import type { PixelImage } from '@/utils/faviconImage';

const NAVY = [24, 42, 71, 255];
const WHITE = [255, 255, 255, 255];

/** Imagen de `size`×`size` con todos los píxeles blancos, salvo los indicados. */
function image(size: number, paint: (x: number, y: number) => number[] | null): PixelImage {
  const data = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      data.set(paint(x, y) ?? WHITE, (y * size + x) * 4);
    }
  }
  return { data, width: size, height: size };
}

const pixel = (img: PixelImage, x: number, y: number) => Array.from(img.data.slice((y * img.width + x) * 4, (y * img.width + x) * 4 + 4));

describe('cutOutBackground', () => {
  it('deja transparente el blanco que rodea al dibujo', () => {
    const img = image(9, (x, y) => (x >= 3 && x <= 5 && y >= 3 && y <= 5 ? NAVY : null));

    cutOutBackground(img);

    expect(pixel(img, 0, 0)[3]).toBe(0);
    expect(pixel(img, 8, 4)[3]).toBe(0);
    expect(pixel(img, 4, 4)).toEqual(NAVY);
  });

  it('conserva los blancos de adentro del dibujo (como el hueco de un tenedor)', () => {
    // Anillo azul con un centro blanco cerrado.
    const img = image(9, (x, y) => {
      const inside = x >= 2 && x <= 6 && y >= 2 && y <= 6;
      const hole = x >= 4 && x <= 4 && y >= 4 && y <= 4;
      return inside && !hole ? NAVY : null;
    });

    cutOutBackground(img);

    expect(pixel(img, 0, 0)[3]).toBe(0);
    expect(pixel(img, 4, 4)).toEqual(WHITE);
  });

  it('una imagen que ya es transparente queda igual', () => {
    const img = image(5, (x, y) => (x === 2 && y === 2 ? NAVY : [0, 0, 0, 0]));

    cutOutBackground(img);

    expect(pixel(img, 0, 0)[3]).toBe(0);
    expect(pixel(img, 2, 2)).toEqual(NAVY);
  });
});

describe('addWhiteOutline', () => {
  it('rodea el dibujo con un borde blanco y deja el resto transparente', () => {
    const img = image(11, (x, y) => (x === 5 && y === 5 ? NAVY : [0, 0, 0, 0]));

    addWhiteOutline(img, 2);

    expect(pixel(img, 5, 5)).toEqual(NAVY);
    expect(pixel(img, 5, 4)).toEqual([255, 255, 255, 255]);
    expect(pixel(img, 7, 5)).toEqual([255, 255, 255, 255]);
    expect(pixel(img, 0, 0)[3]).toBe(0);
  });
});
