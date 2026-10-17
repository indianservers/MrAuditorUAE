"use client";
import { Button, ErrorState, Modal } from "@/components/ui/primitives";
import { downloadCSV, money } from "@/lib/formatting/money";
import { useUI } from "@/stores/workspace";
import type { RecordRow } from "@/types/models";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type ColumnState,
  type GridApi,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Columns3, Download, RotateCcw, Rows3, Save } from "lucide-react";
import { useMemo, useRef, useState } from "react";
ModuleRegistry.registerModules([AllCommunityModule]);
const theme = themeQuartz.withParams({
  fontFamily: "Inter Variable, Arial, sans-serif",
  fontSize: 12,
  headerFontSize: 11,
  foregroundColor: "#14243b",
  headerBackgroundColor: "#f4f6fa",
  borderColor: "#e2e8f0",
  rowBorder: { color: "#edf1f6" },
  selectedRowBackgroundColor: "#e5f2ff",
  accentColor: "#087fff",
  borderRadius: 4,
  wrapperBorderRadius: 4,
  headerColumnBorder: true,
});
export const column = (
  field: string,
  headerName: string,
  width = 140,
  extra: Partial<ColDef<RecordRow>> = {},
): ColDef<RecordRow> => ({ field, headerName, width, ...extra });
export const amount = (
  field: string,
  headerName: string,
  currency = "",
): ColDef<RecordRow> =>
  column(field, headerName + " (" + currency + ")", 132, {
    type: "numericColumn",
    cellClass: "money-cell",
    valueFormatter: (p) => money(p.value),
    comparator: (a, b) => {
      const aa = String(a ?? 0),
        bb = String(b ?? 0);
      const scale = (v: string) => {
        const formatted = money(v, 8);
        if (formatted === "—") return 0n;
        return BigInt(
          (formatted.startsWith("(") ? "-" : "") +
            formatted.replace(/[,.()]/g, ""),
        );
      };
      return scale(aa) < scale(bb) ? -1 : scale(aa) > scale(bb) ? 1 : 0;
    },
  });
export function FinancialDataGrid({
  rows,
  columns,
  onSelect,
  loading = false,
  error = null,
  name = "financial",
  currency = "",
  server = false,
}: {
  rows: RecordRow[];
  columns: ColDef<RecordRow>[];
  onSelect?: (row: RecordRow) => void;
  loading?: boolean;
  error?: Error | null;
  name?: string;
  currency?: string;
  server?: boolean;
}) {
  const ref = useRef<AgGridReact<RecordRow>>(null);
  const { density, setDensity } = useUI();
  const [picker, setPicker] = useState(false),
    [message, setMessage] = useState("");
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const defaults = useMemo<ColDef<RecordRow>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
      minWidth: 95,
      wrapHeaderText: true,
      suppressHeaderMenuButton: false,
    }),
    [],
  );
  const savedKey = "auditos-grid-v3-" + name;
  if (error) return <ErrorState error={error} />;
  function save() {
    const state = ref.current?.api?.getColumnState();
    if (state) {
      localStorage.setItem(savedKey, JSON.stringify(state));
      setMessage("Column view saved");
    }
  }
  function restore(api: GridApi<RecordRow>) {
    try {
      const saved = localStorage.getItem(savedKey);
      if (saved)
        api.applyColumnState({
          state: JSON.parse(saved) as ColumnState[],
          applyOrder: true,
        });
    } catch {
      localStorage.removeItem(savedKey);
    }
  }
  return (
    <div className="financial-grid">
      <div className="grid-tools">
        <span className="subtle">
          {currency ? currency + " · " : ""}
          {server
            ? "Sort & filter within loaded server page"
            : "Sort & filter loaded records"}{" "}
          · Community grid
        </span>
        <div>
          <Button
            onClick={() => {
              setVisible(
                Object.fromEntries(
                  columns.map((c) => [
                    c.colId || c.field!,
                    ref.current?.api
                      ?.getColumn(c.colId || c.field!)
                      ?.isVisible() ?? true,
                  ]),
                ),
              );
              setPicker(true);
            }}
          >
            <Columns3 size={13} /> Columns
          </Button>
          <Button
            onClick={() =>
              setDensity(density === "compact" ? "comfortable" : "compact")
            }
          >
            <Rows3 size={13} />{" "}
            {density === "compact" ? "Compact" : "Comfortable"}
          </Button>
          <Button onClick={save}>
            <Save size={13} /> Save view
          </Button>
          <Button
            aria-label="Reset grid view"
            onClick={() => {
              localStorage.removeItem(savedKey);
              ref.current?.api?.resetColumnState();
              setMessage("View reset");
            }}
          >
            <RotateCcw size={13} />
          </Button>
          <Button
            disabled={!rows.length}
            onClick={() => {
              const displayed: RecordRow[] = [];
              ref.current?.api?.forEachNodeAfterFilterAndSort((n) => {
                if (n.data) displayed.push(n.data);
              });
              downloadCSV(name + "-loaded-page.csv", displayed);
            }}
          >
            <Download size={13} /> CSV · page
          </Button>
        </div>
      </div>
      <span role="status" className="sr-only">
        {message}
      </span>
      <div className="grid-body">
        <AgGridReact<RecordRow>
          ref={ref}
          theme={theme}
          rowData={rows}
          columnDefs={columns}
          defaultColDef={defaults}
          rowHeight={density === "compact" ? 35 : 42}
          headerHeight={44}
          getRowId={(p) => p.data.id}
          suppressPaginationPanel={true}
          selectionColumnDef={{
            pinned: "left",
            width: 38,
            minWidth: 38,
            maxWidth: 38,
            lockPosition: "left",
          }}
          rowSelection={{
            mode: "singleRow",
            enableClickSelection: true,
            checkboxes: true,
          }}
          onRowClicked={(e) => {
            if (e.data) onSelect?.(e.data);
          }}
          onSelectionChanged={(e) => {
            const selected = e.api.getSelectedRows()[0];
            if (selected) onSelect?.(selected);
          }}
          onCellKeyDown={(e) => {
            const key = (e.event as KeyboardEvent)?.key;
            if (key === "Enter" && e.data) onSelect?.(e.data);
          }}
          onGridReady={(e) => restore(e.api)}
          loading={loading}
          overlayNoRowsTemplate="<span>No records in this context</span>"
          animateRows={false}
        />
      </div>
      {!rows.length && !loading && (
        <div className="grid-empty-note">
          Import or select a financial population to begin. No demonstration
          figures are substituted.
        </div>
      )}
      <Modal title="Visible columns" open={picker} onOpenChange={setPicker}>
        <div className="column-picker">
          {columns.map((c) => (
            <label key={c.colId || c.field}>
              <input
                type="checkbox"
                checked={visible[c.colId || c.field!] ?? true}
                onChange={(e) => {
                  const id = c.colId || c.field!;
                  setVisible((v) => ({ ...v, [id]: e.target.checked }));
                  ref.current?.api?.setColumnsVisible([id], e.target.checked);
                }}
              />
              {c.headerName}
            </label>
          ))}
        </div>
      </Modal>
    </div>
  );
}
