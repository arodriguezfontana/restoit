import { IngredientFields } from '@/components/ingredientes/IngredientFields';
import type { Ingredient, IngredientPayload } from '@/types/ingredient';
import { formatCurrency } from '@/utils/currency';

const orDash = (amount?: number | null) => (amount ? formatCurrency(amount) : '—');
const FULL_WIDTH = 'w-full';

interface EditRowProps {
  ingredient: Ingredient;
  draft: IngredientPayload;
  saving: boolean;
  onDraftChange: (draft: IngredientPayload) => void;
  onSave: () => void;
  onCancel: () => void;
}

function EditRow({ ingredient, draft, saving, onDraftChange, onSave, onCancel }: EditRowProps) {
  return (
    <tr className="bg-gray-50/50">
      <IngredientFields
        value={draft}
        onChange={onDraftChange}
        subject="del ingrediente"
        classes={{ name: FULL_WIDTH, unit: FULL_WIDTH, cost: FULL_WIDTH, extra: FULL_WIDTH }}
        inTableCells
      />
      <td className="py-2 px-5 text-gray-500">{ingredient.products_count} productos</td>
      <td className="py-2 px-5 text-right whitespace-nowrap space-x-2">
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="text-xs font-semibold rounded-lg bg-black text-white px-3 py-1.5 hover:bg-gray-800 disabled:opacity-60"
        >
          Guardar
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-xs font-semibold rounded-lg px-3 py-1.5 text-gray-600 hover:bg-gray-200"
        >
          Cancelar
        </button>
      </td>
    </tr>
  );
}

function ReadRow({
  ingredient,
  confirmingDelete,
  onEdit,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: {
  ingredient: Ingredient;
  confirmingDelete?: boolean;
  onEdit: () => void;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}) {
  return (
    <tr className="hover:bg-gray-50/50">
      <td className="py-3 px-5 font-semibold text-gray-900">{ingredient.name}</td>
      <td className="py-3 px-5 text-gray-600">{ingredient.unit}</td>
      <td className="py-3 px-5 text-gray-600 font-medium">{orDash(ingredient.cost)}</td>
      <td className="py-3 px-5 text-gray-600">{orDash(ingredient.extra_price)}</td>
      <td className="py-3 px-5 text-gray-500">
        {ingredient.products_count === 1 ? '1 producto' : `${ingredient.products_count} productos`}
      </td>
      <td className="py-3 px-5 text-right whitespace-nowrap space-x-2">
        {confirmingDelete ? (
          <span className="inline-flex items-center gap-1.5 text-xs">
            <span className="text-red-600 font-semibold text-xs">¿Eliminar?</span>
            <button
              type="button"
              onClick={onConfirmDelete}
              className="px-2.5 py-1 bg-red-600 hover:bg-red-700 text-white rounded-lg font-semibold text-xs transition"
            >
              Sí
            </button>
            <button
              type="button"
              onClick={onCancelDelete}
              className="px-2.5 py-1 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg font-semibold text-xs transition"
            >
              No
            </button>
          </span>
        ) : (
          <>
            <button
              type="button"
              onClick={onEdit}
              aria-label={`Editar ${ingredient.name}`}
              className="text-xs font-semibold rounded-lg px-3 py-1.5 text-gray-700 hover:bg-gray-200"
            >
              Editar
            </button>
            <button
              type="button"
              onClick={onAskDelete}
              aria-label={`Eliminar ${ingredient.name}`}
              className="text-xs font-semibold rounded-lg px-3 py-1.5 text-red-600 hover:bg-red-50"
            >
              Eliminar
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

interface IngredientsTableProps {
  ingredients: Ingredient[];
  editingId: number | null;
  deletingId?: number | null;
  draft: IngredientPayload;
  savingEdit: boolean;
  onDraftChange: (draft: IngredientPayload) => void;
  onStartEditing: (ingredient: Ingredient) => void;
  onSaveEdit: (id: number) => void;
  onCancelEdit: () => void;
  onAskDelete: (ingredient: Ingredient) => void;
  onCancelDelete: () => void;
  onConfirmDelete: (ingredient: Ingredient) => void;
  onDelete?: (ingredient: Ingredient) => void;
}

/** Los ingredientes del local; el que se está editando se muestra con sus campos. */
export function IngredientsTable(props: IngredientsTableProps) {
  return (
    <div className="overflow-auto lg:min-h-0">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-gray-50 text-[11px] font-bold text-gray-500 uppercase tracking-wider">
          <tr>
            <th className="py-3 px-5">Ingrediente</th>
            <th className="py-3 px-5">Unidad</th>
            <th className="py-3 px-5">Costo unitario</th>
            <th className="py-3 px-5">Precio extra</th>
            <th className="py-3 px-5">Usado en</th>
            <th className="py-3 px-5 text-right">Acciones</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {props.ingredients.map((ingredient) =>
            props.editingId === ingredient.id ? (
              <EditRow
                key={ingredient.id}
                ingredient={ingredient}
                draft={props.draft}
                saving={props.savingEdit}
                onDraftChange={props.onDraftChange}
                onSave={() => props.onSaveEdit(ingredient.id)}
                onCancel={props.onCancelEdit}
              />
            ) : (
              <ReadRow
                key={ingredient.id}
                ingredient={ingredient}
                confirmingDelete={props.deletingId === ingredient.id}
                onEdit={() => props.onStartEditing(ingredient)}
                onAskDelete={() => props.onAskDelete(ingredient)}
                onCancelDelete={props.onCancelDelete}
                onConfirmDelete={() => props.onConfirmDelete(ingredient)}
              />
            )
          )}
        </tbody>
      </table>
    </div>
  );
}
