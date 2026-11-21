import { useEffect, useState } from 'react';
import { fetchPredictions } from '@/services/statsService';
import type { PredictionsResponse } from '@/types/stats';
import { formatCurrency } from '@/utils/currency';
import { PanelNote } from '@/components/ui/PanelNote';
import { SparklesIcon } from '@/components/Icons';

export function PredictiveAnalyticsTab() {
  const [data, setData] = useState<PredictionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = () => {
    setLoading(true);
    setError(null);
    fetchPredictions()
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => {
        setError('No se pudieron calcular las predicciones de demanda e insumos. Podés reintentar.');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="py-12">
        <PanelNote>Calculando predicciones de demanda, proyecciones de insumos y prescripciones de IA...</PanelNote>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center space-y-4">
        <p className="text-sm font-semibold text-red-700">{error ?? 'Ocurrió un error inesperado.'}</p>
        <button
          type="button"
          onClick={loadData}
          className="rounded-xl bg-black px-4 py-2 text-xs font-bold text-white hover:bg-gray-800 transition"
        >
          Reintentar predicción
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Banner de Estado de IA / Degradación Controlada */}
      <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-amber-50 text-amber-700">
            <SparklesIcon className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-gray-900">Pronósticos Comerciales y Prescripciones</h3>
              <span
                className={`text-[10px] uppercase font-black px-2 py-0.5 rounded-full ${
                  data.is_ai_generated
                    ? 'bg-purple-100 text-purple-800'
                    : 'bg-blue-100 text-blue-800'
                }`}
              >
                {data.is_ai_generated ? 'Asistido por IA (Gemini)' : 'Estimación Estadística Backend'}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              Proyecciones para los próximos 7 días basadas en las últimas {data.historical_weeks_analyzed} semanas de ventas
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={loadData}
          className="self-start sm:self-auto rounded-xl border border-gray-300 hover:bg-gray-50 px-3 py-1.5 text-xs font-semibold text-gray-700 transition"
        >
          Actualizar pronóstico
        </button>
      </div>

      {data.disclaimer && (
        <div className="rounded-xl bg-blue-50 border border-blue-200 p-4 text-xs text-blue-800 flex items-center justify-between">
          <span>{data.disclaimer}</span>
        </div>
      )}

      {/* KPI Cards de Proyección */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Próximos 7 Días</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(data.total_projected_revenue)}</div>
          <span className="text-xs font-semibold text-gray-600 mt-1">{data.total_projected_orders} pedidos estimados</span>
        </div>

        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between border-l-4 border-l-purple-500">
          <span className="text-xs font-semibold text-purple-700 uppercase tracking-wider">Fin de Semana (Sáb - Dom)</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(data.weekend_projected_revenue)}</div>
          <span className="text-xs font-semibold text-purple-700 mt-1">{data.weekend_projected_orders} pedidos estimados</span>
        </div>

        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Días de Semana (Lun - Vie)</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(data.weekday_projected_revenue)}</div>
          <span className="text-xs font-semibold text-gray-600 mt-1">{data.weekday_projected_orders} pedidos estimados</span>
        </div>

        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Promedio Diario</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(data.avg_daily_revenue)}</div>
          <span className="text-xs text-gray-400 mt-1">{data.avg_daily_orders} pedidos / día</span>
        </div>
      </div>

      {/* Proyección Día a Día (7 días) */}
      <div className="bg-white rounded-2xl shadow-xs border border-gray-100 p-5">
        <h4 className="text-sm font-bold text-gray-900 mb-1">Volumen y Facturación Estimada por Día</h4>
        <p className="text-xs text-gray-500 mb-4">
          Estimación diaria diferenciando la concentración de demanda de fin de semana
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {data.days.map((day) => (
            <div
              key={day.date}
              className={`p-3.5 rounded-xl border flex flex-col justify-between transition ${
                day.is_weekend
                  ? 'bg-purple-50/50 border-purple-200'
                  : 'bg-gray-50/50 border-gray-200'
              }`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black text-gray-900">{day.day_name}</span>
                  {day.is_weekend && (
                    <span className="text-[9px] bg-purple-200 text-purple-900 font-bold px-1.5 py-0.5 rounded">
                      Finde
                    </span>
                  )}
                </div>
                <span className="text-[11px] text-gray-400 block">{day.date}</span>
              </div>

              <div className="mt-3">
                <span className="text-sm font-black text-gray-900 block">{formatCurrency(day.projected_revenue)}</span>
                <span className="text-xs font-medium text-gray-600">{day.projected_orders} pedidos</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Demanda Proyectada de Insumos Principales */}
      <div className="bg-white rounded-2xl shadow-xs border border-gray-100 overflow-hidden">
        <div className="p-5 border-b border-gray-100">
          <h4 className="text-base font-bold text-gray-900">Demanda Proyectada de Insumos Principales</h4>
          <p className="text-xs text-gray-500 mt-0.5">
            Materias primas requeridas para los próximos 7 días calculadas según las recetas de los platos con mayor tendencia de venta
          </p>
        </div>

        {data.ingredient_demands.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-500">
            No hay suficientes ventas históricas de platos con receta configurada para proyectar insumos.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-gray-50/75 border-b border-gray-100 text-gray-600 font-semibold">
                  <th className="py-3 px-4">Insumo Requerido</th>
                  <th className="py-3 px-4">Demanda Proyectada</th>
                  <th className="py-3 px-4 text-right">Costo Unitario</th>
                  <th className="py-3 px-4 text-right">Gasto Estimado</th>
                  <th className="py-3 px-4">Platos Principales</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.ingredient_demands.map((ing) => (
                  <tr key={ing.ingredient_id} className="hover:bg-gray-50/50 transition">
                    <td className="py-3 px-4 font-bold text-gray-900">{ing.ingredient_name}</td>
                    <td className="py-3 px-4 font-bold text-purple-700">
                      {ing.projected_quantity} {ing.unit}
                    </td>
                    <td className="py-3 px-4 text-right text-gray-600">{formatCurrency(ing.unit_cost)}</td>
                    <td className="py-3 px-4 text-right font-black text-gray-900">{formatCurrency(ing.estimated_cost)}</td>
                    <td className="py-3 px-4 text-gray-500 truncate max-w-xs">
                      {ing.contributing_products.join(', ') || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Prescripciones Estratégicas y de Compras */}
      <div className="bg-white rounded-2xl shadow-xs border border-gray-100 p-6">
        <div className="flex items-center gap-2 mb-4">
          <div className="p-1.5 rounded-lg bg-black text-white">
            <SparklesIcon className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-base font-bold text-gray-900">Recomendaciones Estratégicas de Compras y Operaciones</h4>
            <p className="text-xs text-gray-500">Pautas de acción recomendadas para optimizar compras y abastecimiento</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data.strategic_prescriptions.map((prescription, idx) => (
            <div
              key={idx}
              className="p-4 rounded-xl bg-gray-50 border border-gray-100 text-xs text-gray-800 leading-relaxed flex gap-3"
            >
              <span className="font-black text-amber-600 text-sm">#{idx + 1}</span>
              <div>{prescription}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
