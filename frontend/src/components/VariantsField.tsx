import { INPUT_FULL_CLASS as INPUT_CLASS, LABEL_CLASS } from '@/styles/forms';
import type { VariantDraft } from '@/utils/variantDrafts';

interface VariantsFieldProps {
  drafts: VariantDraft[];
  onChange: (drafts: VariantDraft[]) => void;
}

/** Variantes del producto con su precio (ej. Grande y Chica, o Carne y Pollo). */
export function VariantsField({ drafts, onChange }: VariantsFieldProps) {
  const update = (index: number, change: Partial<VariantDraft>) =>
    onChange(drafts.map((draft, i) => (i === index ? { ...draft, ...change } : draft)));

  return (
    <fieldset className="space-y-2">
      <legend className={LABEL_CLASS}>Variantes</legend>
      <p className="text-[11px] text-gray-500 -mt-1">
        Opciones con su propio precio, como Grande y Chica o Carne y Pollo. El cliente elige una al pedir.
      </p>
      {drafts.map((draft, index) => (
        <div key={index} className="flex items-center gap-2">
          <input
            type="text"
            value={draft.name}
            onChange={(e) => update(index, { name: e.target.value })}
            placeholder="Nombre (ej. Grande)"
            maxLength={50}
            aria-label={`Nombre de la variante ${index + 1}`}
            className={INPUT_CLASS}
          />
          <div className="relative w-40 shrink-0">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400">$</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={draft.price}
              onChange={(e) => update(index, { price: e.target.value })}
              aria-label={`Precio de la variante ${index + 1}`}
              className={`${INPUT_CLASS} pl-7`}
            />
          </div>
          <button
            type="button"
            onClick={() => onChange(drafts.filter((_, i) => i !== index))}
            aria-label={`Quitar la variante ${draft.name || index + 1}`}
            className="w-9 h-9 shrink-0 rounded-lg border border-gray-300 text-gray-500 hover:bg-gray-100 transition"
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...drafts, { name: '', price: '' }])}
        className="text-sm font-semibold text-gray-700 underline hover:no-underline"
      >
        + Agregar variante
      </button>
    </fieldset>
  );
}
