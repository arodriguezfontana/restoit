import { useEffect, useRef, useState } from 'react';

const COPIED_MS = 2000;

/** Botón que copia un texto al portapapeles y avisa un instante que ya está copiado. */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    []
  );

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return;
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), COPIED_MS);
  };

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={`Copiar ${label}`}
      className="shrink-0 text-xs font-semibold px-2.5 py-1 rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-100 transition"
    >
      {copied ? '¡Copiado!' : 'Copiar'}
    </button>
  );
}
