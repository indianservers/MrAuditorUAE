import type { components } from "./api.generated";
export type Client = components["schemas"]["ClientOut"];
export type Entity = components["schemas"]["EntityOut"];
export type Engagement = components["schemas"]["EngagementOut"];
export type Period = components["schemas"]["PeriodOut"];
export type Page<T> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};
// Generic Phase 2 resource serializers publish open dictionaries in OpenAPI.
export type RecordRow = { id: string; [key: string]: unknown };
export type BalanceRow = RecordRow & {
  code: string;
  name: string;
  classification: string | null;
  opening: string;
  debit: string;
  credit: string;
  closing: string;
  display_closing: string;
};
export type Balance = Page<BalanceRow> & {
  functional_currency: string;
  balanced: boolean;
  debit_credit_difference: string;
  total_debit: string;
  total_credit: string;
  mapped_accounts: number;
  unmapped_accounts: number;
};
export type Access = { tenant_id: string; permissions: string[] };
