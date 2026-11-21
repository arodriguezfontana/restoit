import { useCallback, useMemo, useState } from 'react';
import { OrderDetailModal } from '@/components/OrderDetailModal';
import { BoardToolbar } from '@/components/comandas/BoardToolbar';
import { OrderColumn } from '@/components/comandas/OrderColumn';
import { SectorTabs } from '@/components/comandas/SectorTabs';
import { SoundAlertNotices } from '@/components/comandas/SoundAlertNotices';
import { UnpaidFinishModal } from '@/components/comandas/UnpaidFinishModal';
import { PanelNote } from '@/components/ui/PanelNote';
import { useBoardActions } from '@/hooks/useBoardActions';
import { useBoardData } from '@/hooks/useBoardData';
import { useBoardFilters } from '@/hooks/useBoardFilters';
import { useNewOrderAlert } from '@/hooks/useNewOrderAlert';
import { getThemeOption, type ThemeColor } from '@/types/storeConfig';
import { buildColumns, buildTripsToStart, countActiveOrdersBySector } from '@/utils/orderBoard';

interface ComandasBoardProps {
  /** Acceso rápido a la sección para cargar pedidos presenciales. */
  onTakeOrder?: () => void;
  themeColor?: ThemeColor;
}

export function ComandasBoard({ onTakeOrder, themeColor }: ComandasBoardProps) {
  const themeHex = themeColor ? getThemeOption(themeColor).hex : undefined;
  const { orders, setOrders, activeDrivers, loading, hasLoaded, error, setError } = useBoardData();
  const filters = useBoardFilters();
  const actions = useBoardActions({ orders, setOrders, setError });

  const [detailOrderId, setDetailOrderId] = useState<number | null>(null);
  const closeDetail = useCallback(() => setDetailOrderId(null), []);
  // Se busca en la lista para que la ventana refleje el estado actualizado por el sondeo.
  const detailOrder = orders.find((order) => order.id === detailOrderId) ?? null;

  // Suena mientras haya pedidos nuevos que el personal todavía no vio y, con otro sonido, pedidos con productos que
  // cocina todavía no vio.
  const newOrderIds = useMemo(() => orders.filter((o) => o.needs_attention).map((o) => o.id), [orders]);
  const modifiedOrderIds = useMemo(
    () => orders.filter((o) => o.status === 'Confirmado' && o.kitchen_update_pending).map((o) => o.id),
    [orders]
  );
  const soundAlert = useNewOrderAlert(newOrderIds, undefined, modifiedOrderIds);

  const sectorCounts = useMemo(() => countActiveOrdersBySector(orders), [orders]);
  const columns = useMemo(
    () =>
      buildColumns(orders, {
        selectedSector: filters.selectedSector,
        timingFilter: filters.timingFilter,
        pages: filters.pages,
        pageSize: filters.pageSize,
        searchTerm: filters.searchTerm,
      }),
    [orders, filters.selectedSector, filters.timingFilter, filters.pages, filters.pageSize, filters.searchTerm]
  );
  const noSearchResults = Boolean(filters.searchTerm) && columns.every((column) => column.totalCount === 0);
  // Viajes por armar: pedidos a domicilio "En Camino" que todavía no salieron, agrupados por repartidor.
  const tripsToStart = useMemo(() => buildTripsToStart(orders), [orders]);

  const cardProps = {
    activeDrivers,
    selectedSector: filters.selectedSector,
    onAssignDriver: actions.handleAssignDriver,
    onStatusChange: actions.handleStatusChange,
    onMarkPaid: actions.handleMarkPaid,
    onAcknowledgeUpdate: actions.handleAcknowledgeUpdate,
    onMarkSeen: actions.handleMarkSeen,
    onItemPreparedChange: actions.handleItemPreparedChange,
    onSectorPrepared: actions.handleSectorPrepared,
    onOpenDetail: (selected: { id: number; needs_attention?: boolean }) => {
      setDetailOrderId(selected.id);
      // Abrir el pedido nuevo cuenta como verlo: se apaga su alerta.
      if (selected.needs_attention) void actions.handleMarkSeen(selected.id);
    },
  };

  return (
    <div className="flex flex-col gap-4 lg:h-full">
      <BoardToolbar
        onTakeOrder={onTakeOrder}
        themeHex={themeHex}
        pageSize={filters.pageSize}
        onPageSizeChange={filters.setPageSize}
        searchInput={filters.searchInput}
        onSearchChange={filters.setSearchInput}
        onSearchClear={filters.clearSearch}
        soundEnabled={soundAlert.enabled}
        soundSupported={soundAlert.audioSupported}
        onToggleSound={soundAlert.toggleEnabled}
      />

      <SectorTabs selected={filters.selectedSector} counts={sectorCounts} onChange={filters.changeSector} />

      <SoundAlertNotices
        supported={soundAlert.audioSupported}
        enabled={soundAlert.enabled}
        blocked={soundAlert.audioBlocked}
        onUnlock={soundAlert.unlockAudio}
      />

      {error && <div className="shrink-0 rounded-xl bg-red-50 text-red-700 px-4 py-3 text-sm">{error}</div>}

      {loading && !hasLoaded && orders.length === 0 ? (
        <PanelNote>Cargando comandas...</PanelNote>
      ) : noSearchResults ? (
        <PanelNote>{`No se encontraron comandas para '${filters.searchTerm}'.`}</PanelNote>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 lg:grid-rows-1 gap-4 items-start lg:items-stretch lg:flex-1 lg:min-h-0">
          {columns.map((column) => (
            <OrderColumn
              key={column.status}
              column={column}
              selectedSector={filters.selectedSector}
              searchTerm={filters.searchTerm}
              timingFilter={filters.timingFilter}
              onTimingFilterChange={filters.changeTimingFilter}
              tripsToStart={tripsToStart}
              dispatchingDriverId={actions.dispatchingDriverId}
              onStartTrip={actions.handleStartTrip}
              onPageChange={(page) => filters.changePage(column.status, page)}
              cardProps={cardProps}
            />
          ))}
        </div>
      )}

      {detailOrder && (
        <OrderDetailModal
          key={detailOrder.id}
          order={detailOrder}
          onMarkPaid={actions.handleMarkPaid}
          onAcknowledgeUpdate={actions.handleAcknowledgeUpdate}
          onUpdateDelay={actions.handleUpdateDelay}
          onCancel={(orderId) => actions.handleStatusChange(orderId, 'Cancelado')}
          onClose={closeDetail}
        />
      )}

      {actions.unpaidToFinish && (
        <UnpaidFinishModal
          order={actions.unpaidToFinish}
          saving={actions.finishingUnpaid}
          onConfirm={actions.handlePayAndFinish}
          onCancel={actions.dismissUnpaidToFinish}
        />
      )}
    </div>
  );
}
