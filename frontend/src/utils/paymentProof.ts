import { PROOF_MAX_BYTES } from '@/services/orderService';
import type { AdminOrder, PaymentProofInfo } from '@/types/order';

const PROOF_FORMATS = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

export const PROOF_EXPIRATION_HOURS = 48;
export const PROOF_EXPIRATION_MS = PROOF_EXPIRATION_HOURS * 60 * 60 * 1000;

/** El problema de un archivo elegido como comprobante, o null si sirve. */
export function proofFileProblem(file: File): string | null {
  if (!PROOF_FORMATS.includes(file.type)) return 'El comprobante tiene que ser un archivo JPG, PNG, WEBP o PDF.';
  return file.size > PROOF_MAX_BYTES ? 'El comprobante no puede pesar más de 5 MB.' : null;
}

/** Indica si pasaron las 48 h de vigencia del comprobante o del pedido. */
export function isPaymentProofExpired(
  order?: Pick<AdminOrder, 'created_at'> | null,
  proof?: PaymentProofInfo | null,
  now: number = Date.now()
): boolean {
  if (proof?.expires_at) {
    const expiresMs = new Date(proof.expires_at).getTime();
    if (!Number.isNaN(expiresMs) && expiresMs <= now) return true;
  }
  if (proof?.uploaded_at) {
    const uploadedMs = new Date(proof.uploaded_at).getTime();
    if (!Number.isNaN(uploadedMs) && now - uploadedMs >= PROOF_EXPIRATION_MS) return true;
  }
  if (order?.created_at) {
    const createdMs = new Date(order.created_at).getTime();
    if (!Number.isNaN(createdMs) && now - createdMs >= PROOF_EXPIRATION_MS) return true;
  }
  return false;
}

