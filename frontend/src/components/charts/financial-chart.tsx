"use client";
import { Empty } from "@/components/ui/primitives";
import * as echarts from "echarts";
import { useEffect, useRef } from "react";
export type ChartDatum = { name: string; value: number };
export function FinancialChart({
  title,
  data,
  type = "bar",
  onSelect,
  unit = "findings",
}: {
  title: string;
  data: ChartDatum[];
  type?: "bar" | "line" | "donut";
  onSelect?: (name: string) => void;
  unit?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current || !data.length) return;
    const chart = echarts.init(el.current);
    const colors = ["#0788ff", "#10bfa3", "#f3b447", "#ef5865", "#9668e8"];
    chart.setOption({
      animation: false,
      color: colors,
      tooltip: {
        trigger: type === "donut" ? "item" : "axis",
        valueFormatter: (v: unknown) => `${String(v)} ${unit}`,
      },
      grid: { left: 45, right: 15, top: 15, bottom: 40 },
      xAxis:
        type === "donut"
          ? undefined
          : {
              type: "category",
              data: data.map((d) => d.name),
              axisLabel: { fontSize: 10, color: "#66788f", hideOverlap: true },
              axisLine: { lineStyle: { color: "#e2e8f0" } },
            },
      yAxis:
        type === "donut"
          ? undefined
          : {
              type: "value",
              minInterval: 1,
              axisLabel: { fontSize: 10, color: "#66788f" },
              splitLine: { lineStyle: { color: "#edf1f6" } },
            },
      series: [
        type === "donut"
          ? {
              type: "pie",
              radius: ["58%", "80%"],
              center: ["50%", "48%"],
              label: { show: false },
              data,
            }
          : {
              type,
              showSymbol: false,
              smooth: false,
              areaStyle: type === "line" ? { opacity: 0.1 } : undefined,
              barMaxWidth: 45,
              data: data.map((d, i) => ({
                value: d.value,
                itemStyle: { color: colors[i % colors.length] },
              })),
            },
      ],
    });
    chart.on("click", (p) => onSelect?.(p.name));
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [data, type, onSelect, unit]);
  return (
    <section className="card chart-card">
      <h3>
        {title}
        <small>{unit}</small>
      </h3>
      {data.length ? (
        <>
          <div ref={el} className="chart" role="img" aria-label={title} />
          <details className="chart-alternative">
            <summary>
              Accessible data{onSelect ? " · select to filter" : ""}
            </summary>
            <div>
              {data.map((d) => (
                <button
                  disabled={!onSelect}
                  key={d.name}
                  onClick={() => onSelect?.(d.name)}
                >
                  {d.name}: {d.value.toLocaleString()} {unit}
                </button>
              ))}
            </div>
          </details>
        </>
      ) : (
        <Empty title="No chart data">
          Run the corresponding backend workflow in this context.
        </Empty>
      )}
    </section>
  );
}
export function RiskHeatmap({
  data,
  onSelect,
}: {
  data: { group: string; rule: string; value: number }[];
  onSelect: (rule: string) => void;
}) {
  const groups = [...new Set(data.map((d) => d.group))],
    rules = [...new Set(data.map((d) => d.rule))].slice(0, 8);
  return (
    <section className="card heatmap">
      <h3>
        Exception concentration by account group
        <small>Finding counts · selected run</small>
      </h3>
      {data.length ? (
        <div className="heatmap-scroll">
          <table>
            <thead>
              <tr>
                <th>Account group</th>
                {rules.map((r) => (
                  <th key={r}>{r}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g}>
                  <th>{g}</th>
                  {rules.map((r) => {
                    const value =
                      data.find((d) => d.group === g && d.rule === r)?.value ||
                      0;
                    return (
                      <td key={r}>
                        <button
                          className={
                            value > 10
                              ? "heat-high"
                              : value > 3
                                ? "heat-medium"
                                : "heat-low"
                          }
                          aria-label={`${g}, ${r}: ${value} findings`}
                          onClick={() => onSelect(r)}
                        >
                          {value}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="No account concentration data" />
      )}
    </section>
  );
}
