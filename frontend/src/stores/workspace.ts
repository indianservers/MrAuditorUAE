import { create } from "zustand";
import { persist } from "zustand/middleware";
type UI = {
  collapsed: boolean;
  dark: boolean;
  density: "compact" | "comfortable";
  panelWidth: number;
  toggleSidebar: () => void;
  toggleTheme: () => void;
  setDensity: (v: "compact" | "comfortable") => void;
  setPanelWidth: (v: number) => void;
};
export const useUI = create<UI>()(
  persist(
    (set) => ({
      collapsed: false,
      dark: false,
      density: "compact",
      panelWidth: 310,
      toggleSidebar: () => set((s) => ({ collapsed: !s.collapsed })),
      toggleTheme: () => set((s) => ({ dark: !s.dark })),
      setDensity: (density) => set({ density }),
      setPanelWidth: (panelWidth) => set({ panelWidth }),
    }),
    { name: "auditos-ui-v3" },
  ),
);
// Only non-sensitive layout preferences persist. Business selection lives in memory.
type Scope = {
  country: string;
  setCountry: (v: string) => void;
  tenant: string;
  client: string;
  entity: string;
  period: string;
  snapshot: string;
  setTenant: (v: string) => void;
  setClient: (v: string) => void;
  setEntity: (v: string) => void;
  setPeriod: (v: string) => void;
  setSnapshot: (v: string) => void;
};
export const useScope = create<Scope>((set) => ({
  country: "AE",
  setCountry: (country) =>
    set({ country, client: "", entity: "", period: "", snapshot: "" }),
  tenant: "",
  client: "",
  entity: "",
  period: "",
  snapshot: "",
  setTenant: (tenant) =>
    set({
      tenant,
      country: "AE",
      client: "",
      entity: "",
      period: "",
      snapshot: "",
    }),
  setClient: (client) => set({ client, entity: "", period: "", snapshot: "" }),
  setEntity: (entity) => set({ entity, period: "", snapshot: "" }),
  setPeriod: (period) => set({ period, snapshot: "" }),
  setSnapshot: (snapshot) => set({ snapshot }),
}));
