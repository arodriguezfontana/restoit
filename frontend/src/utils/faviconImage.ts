/**
 * Arma el favicon a partir del logo del local: le quita el fondo blanco (solo el que rodea al dibujo, no los blancos
 * de adentro) y le agrega un contorno blanco fino para que se lea sobre pestañas oscuras.
 */

/** Lado del favicon generado: el navegador lo reduce al tamaño de la pestaña. */
const FAVICON_SIZE = 128;
/** Un píxel con todos sus canales por encima de esto se considera fondo blanco. */
const WHITE_THRESHOLD = 225;
/** Valor más oscuro que se toma como color pleno del dibujo (para suavizar los bordes). */
const SOLID_FROM = 70;
const OUTLINE_RATIO = 0.012;

export interface PixelImage {
  data: Uint8ClampedArray;
  width: number;
  height: number;
}

function isBackground(data: Uint8ClampedArray, offset: number): boolean {
  if (data[offset + 3] < 10) return true;
  return Math.min(data[offset], data[offset + 1], data[offset + 2]) >= WHITE_THRESHOLD;
}

/** Máscara de los píxeles de fondo conectados con el borde de la imagen. */
function backgroundMask({ data, width, height }: PixelImage): Uint8Array {
  const mask = new Uint8Array(width * height);
  const stack: number[] = [];
  const push = (x: number, y: number) => {
    const index = y * width + x;
    if (mask[index] || !isBackground(data, index * 4)) return;
    mask[index] = 1;
    stack.push(index);
  };
  for (let x = 0; x < width; x++) {
    push(x, 0);
    push(x, height - 1);
  }
  for (let y = 0; y < height; y++) {
    push(0, y);
    push(width - 1, y);
  }
  while (stack.length > 0) {
    const index = stack.pop() as number;
    const x = index % width;
    const y = Math.floor(index / width);
    if (x > 0) push(x - 1, y);
    if (x < width - 1) push(x + 1, y);
    if (y > 0) push(x, y - 1);
    if (y < height - 1) push(x, y + 1);
  }
  return mask;
}

/** Deja transparente el fondo que rodea al dibujo y suaviza su borde (modifica la imagen). */
export function cutOutBackground(image: PixelImage): void {
  const { data, width, height } = image;
  const mask = backgroundMask(image);
  const touchesBackground = (x: number, y: number) =>
    (x > 0 && mask[y * width + x - 1] === 1) ||
    (x < width - 1 && mask[y * width + x + 1] === 1) ||
    (y > 0 && mask[(y - 1) * width + x] === 1) ||
    (y < height - 1 && mask[(y + 1) * width + x] === 1);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const index = y * width + x;
      const offset = index * 4;
      if (mask[index]) {
        data[offset + 3] = 0;
        continue;
      }
      if (!touchesBackground(x, y)) continue;
      // Píxel de borde: mezcla del dibujo con el blanco; se recupera el color original y se usa como transparencia.
      const alpha = Math.min(1, Math.max(0.05, (255 - Math.min(data[offset], data[offset + 1], data[offset + 2])) / (255 - SOLID_FROM)));
      for (let c = 0; c < 3; c++) data[offset + c] = Math.max(0, Math.min(255, 255 - (255 - data[offset + c]) / alpha));
      data[offset + 3] = Math.round(alpha * data[offset + 3]);
    }
  }
}

/** Agrega un contorno blanco de `radius` píxeles alrededor de lo que no es transparente (modifica la imagen). */
export function addWhiteOutline(image: PixelImage, radius: number): void {
  const { data, width, height } = image;
  const original = new Uint8ClampedArray(data);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const offset = (y * width + x) * 4;
      const alpha = original[offset + 3] / 255;
      if (alpha >= 1) continue;
      let outline = 0;
      for (let dy = -radius; dy <= radius && outline < 1; dy++) {
        for (let dx = -radius; dx <= radius; dx++) {
          const nx = x + dx;
          const ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= width || ny >= height || dx * dx + dy * dy > radius * radius) continue;
          outline = Math.max(outline, original[(ny * width + nx) * 4 + 3] / 255);
        }
      }
      const resultAlpha = alpha + outline * (1 - alpha);
      if (resultAlpha === 0) continue;
      for (let c = 0; c < 3; c++) {
        data[offset + c] = (original[offset + c] * alpha + 255 * outline * (1 - alpha)) / resultAlpha;
      }
      data[offset + 3] = Math.round(resultAlpha * 255);
    }
  }
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('No se pudo cargar el logo.'));
    image.src = url;
  });
}

/**
 * El favicon del logo (PNG como Data URL, sin fondo blanco y con contorno). Si el navegador no puede procesar la
 * imagen (por ejemplo, un logo de otro sitio sin permiso de lectura) devuelve null y se usa el logo tal cual.
 */
export async function buildFaviconFromLogo(logoUrl: string): Promise<string | null> {
  try {
    const image = await loadImage(logoUrl);
    const side = FAVICON_SIZE;
    // Se deja un pequeño margen para que entre el contorno.
    const inner = side - 2 * Math.round(side * 0.04);
    const scale = Math.min(inner / image.naturalWidth, inner / image.naturalHeight);
    const width = Math.max(1, Math.round(image.naturalWidth * scale));
    const height = Math.max(1, Math.round(image.naturalHeight * scale));
    const canvas = document.createElement('canvas');
    canvas.width = side;
    canvas.height = side;
    const context = canvas.getContext('2d');
    if (!context) return null;
    context.drawImage(image, (side - width) / 2, (side - height) / 2, width, height);
    const pixels = context.getImageData(0, 0, side, side);
    cutOutBackground(pixels);
    addWhiteOutline(pixels, Math.max(1, Math.round(side * OUTLINE_RATIO)));
    context.putImageData(pixels, 0, 0);
    return canvas.toDataURL('image/png');
  } catch {
    return null;
  }
}
