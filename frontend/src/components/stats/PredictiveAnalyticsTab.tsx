import { useEffect, useState } from 'react';
import { fetchPredictions } from '@/services/statsService';
import type { PredictionsResponse } from '@/types/stats';
import { formatCurrency } from '@/utils/currency';
import { formatQuantity } from '@/utils/ingredients';
import { PanelNote } from '@/components/ui/PanelNote';

interface PredictiveAnalyticsTabProps {
  refreshKey?: number;
}

export function PredictiveAnalyticsTab({ refreshKey }: PredictiveAnalyticsTabProps = {}) {
  const [data, setData] = useState<PredictionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const PAGE_SIZE = 6;

  const [prevRefreshKey, setPrevRefreshKey] = useState(refreshKey);
  if (refreshKey !== prevRefreshKey) {
    setPrevRefreshKey(refreshKey);
    setLoading(true);
  }

  const handleRetry = () => {
    setLoading(true);
    setError(null);
    fetchPredictions()
      .then((res) => {
        setData(res);
      })
      .catch(() => {
        setError('No se pudieron calcular las predicciones de demanda e insumos. Podés reintentar.');
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    let cancelled = false;
    fetchPredictions()
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('No se pudieron calcular las predicciones de demanda e insumos. Podés reintentar.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

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
          onClick={handleRetry}
          className="rounded-xl bg-black px-4 py-2 text-xs font-bold text-white hover:bg-gray-800 transition"
        >
          Reintentar predicción
        </button>
      </div>
    );
  }

  const peakDay =
    data && data.days.length > 0
      ? [...data.days].sort((a, b) => b.projected_revenue - a.projected_revenue)[0]
      : null;

  return (
    <div className="flex flex-col gap-6">
      {data.disclaimer && (
        <div className="rounded-xl bg-blue-50 border border-blue-200 p-4 text-xs text-blue-800 flex items-center justify-between">
          <span>{data.disclaimer}</span>
        </div>
      )}

      {/* KPI Cards de Proyección: Orden solicitado: total 7 días, promedio diario, día con más ventas (único en violeta), días de semana, fin de semana */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {/* 1. Total Próximos 7 Días */}
        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Próximos 7 Días</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(data.total_projected_revenue)}</div>
          <span className="text-xs font-medium text-gray-500 mt-1">{data.total_projected_orders} pedidos estimados</span>
        </div>

        {/* 2. Promedio Diario */}
        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Promedio Diario</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(data.avg_daily_revenue)}</div>
          <span className="text-xs font-medium text-gray-500 mt-1">{data.avg_daily_orders} pedidos / día</span>
        </div>

        {/* 3. Día con Más Ventas (único en violeta, fondo blanco) */}
        <div className="bg-white p-5 rounded-2xl shadow-xs border border-purple-200 flex flex-col justify-between border-l-4 border-l-purple-600">
          <span className="text-xs font-semibold text-purple-700 uppercase tracking-wider">Día con Más Ventas</span>
          <div className="mt-2">
            <div className="text-2xl font-black text-purple-950">{peakDay?.day_name ?? 'Sin datos'}</div>
            <div className="text-xs font-semibold text-purple-700 mt-0.5">
              {formatCurrency(peakDay?.projected_revenue ?? 0)}
            </div>
          </div>
          <span className="text-xs font-medium text-purple-600 mt-1">
            {peakDay?.projected_orders ?? 0} pedidos estimados
          </span>
        </div>

        {/* 4. Días de Semana */}
        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Días de Semana</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(data.weekday_projected_revenue)}</div>
          <span className="text-xs font-medium text-gray-500 mt-1">{data.weekday_projected_orders} pedidos estimados</span>
        </div>

        {/* 5. Fin de Semana */}
        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Fin de Semana</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(data.weekend_projected_revenue)}</div>
          <span className="text-xs font-medium text-gray-500 mt-1">{data.weekend_projected_orders} pedidos estimados</span>
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
                </div>
                <span className="text-[11px] text-gray-400 block">{day.date}</span>
              </div>

              <div className="mt-3">
                <span className="text-sm font-semibold text-purple-700 block">
                  {formatCurrency(day.projected_orders === 0 ? 0 : day.projected_revenue)}
                </span>
                <span className="text-xs font-semibold text-gray-600">{day.projected_orders} pedidos</span>
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
          (() => {
            const totalDemands = data.ingredient_demands.length;
            const totalPages = Math.max(1, Math.ceil(totalDemands / PAGE_SIZE));
            const paginatedDemands = data.ingredient_demands.slice(
              (currentPage - 1) * PAGE_SIZE,
              currentPage * PAGE_SIZE
            );

            return (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-gray-50/75 border-b border-gray-100 text-gray-600 font-semibold">
                        <th className="py-3 px-4">Insumo Requerido</th>
                        <th className="py-3 px-4">Demanda Proyectada</th>
                        <th className="py-3 px-4 text-right">Costo Unitario</th>
                        <th className="py-3 px-4 text-right">Gasto Estimado</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {paginatedDemands.map((ing) => (
                        <tr key={ing.ingredient_id} className="hover:bg-gray-50/50 transition">
                          <td className="py-3 px-4 font-bold text-gray-900">{ing.ingredient_name}</td>
                          <td className="py-3 px-4 font-bold text-purple-700">
                            {formatQuantity(ing.projected_quantity, ing.unit)}
                          </td>
                          <td className="py-3 px-4 text-right text-gray-600">{formatCurrency(ing.unit_cost)}</td>
                          <td className="py-3 px-4 text-right font-black text-gray-900">{formatCurrency(ing.estimated_cost)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {totalDemands > PAGE_SIZE && (
                  <div className="p-4 border-t border-gray-100 flex flex-col sm:flex-row items-center justify-between gap-3 bg-gray-50/50">
                    <span className="text-xs text-gray-500 font-medium">
                      Mostrando {(currentPage - 1) * PAGE_SIZE + 1} a {Math.min(currentPage * PAGE_SIZE, totalDemands)} de {totalDemands} insumos proyectados
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                        className="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
                      >
                        Anterior
                      </button>
                      <span className="text-xs font-bold text-gray-800 px-2">
                        {currentPage} de {totalPages}
                      </span>
                      <button
                        type="button"
                        onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                        disabled={currentPage === totalPages}
                        className="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
                      >
                        Siguiente
                      </button>
                    </div>
                  </div>
                )}
              </>
            );
          })()
        )}
      </div>
    </div>
  );
}
