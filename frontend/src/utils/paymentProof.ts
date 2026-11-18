import { PROOF_MAX_BYTES } from '@/services/orderService';

const PROOF_FORMATS = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

/** El problema de un archivo elegido como comprobante, o null si sirve. */
export function proofFileProblem(file: File): string | null {
  if (!PROOF_FORMATS.includes(file.type)) return 'El comprobante tiene que ser un archivo JPG, PNG, WEBP o PDF.';
  return file.size > PROOF_MAX_BYTES ? 'El comprobante no puede pesar más de 5 MB.' : null;
}
