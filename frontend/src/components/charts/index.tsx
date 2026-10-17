"use client";
import { Loading } from "@/components/ui/primitives";
import dynamic from "next/dynamic";
export const Chart = dynamic(
  () => import("./financial-chart").then((m) => m.FinancialChart),
  { ssr: false, loading: () => <Loading /> },
);
export const Heatmap = dynamic(
  () => import("./financial-chart").then((m) => m.RiskHeatmap),
  { ssr: false, loading: () => <Loading /> },
);
