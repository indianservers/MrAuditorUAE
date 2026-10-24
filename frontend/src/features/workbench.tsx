"use client";
import { navigation } from "@/components/navigation/routes";
import { Empty } from "@/components/ui/primitives";
import { useAccess } from "@/hooks/use-api";
import { useScope } from "@/stores/workspace";
import { motion, useReducedMotion } from "motion/react";
import { Analytics, Sampling } from "./analytics";
import { Clients } from "./clients";
import { Copilot } from "./copilot";
import { Dashboard } from "./dashboard";
import { Engagements } from "./engagements";
import { Ledger, Mapping, TrialBalance } from "./financials";
import { Integrations, ZohoCallback } from "./integrations";
import { Reconciliation } from "./reconciliation";
import { Compliance, Supporting } from "./supporting";
import { TaxStudio } from "./tax-studio";
import { VATStudio } from "./vat-studio";
import { TPStudio } from "./tp-studio";
import { GRCStudio, BoardPortal } from "./grc-studio";
import { EnterpriseAI } from "./enterprise-ai";
import { Phase9Studio } from "./phase9-studio";
import { IFRSStudio } from "./ifrs-studio";
import { CountrySettings } from "./country-settings";
import {
  ModuleDirectory,
  EngagementWorkspace,
  GroupWorkspace,
  RecordHub,
} from "./global-workspace";
import { WorkingPaperGraph } from "./working-paper-graph";
import { AccountingIntelligence } from "./accounting-intelligence";
import { RegulatoryLibrary } from "./regulatory-library";
import { StatutoryPractice } from "./statutory-practice";
import { StatutoryReportBuilder } from "./statutory-report-builder";
import { IndiaFinancialReporting } from "./india-financial-reporting";
import { CountryCompliance } from "./country-compliance";
import {ClientCollaboration} from "./client-collaboration";
import { AuditStudio } from "./audit-studio";
import { AuditAdministration, ClientPortal } from "./audit-administration";
export function Workbench({ route }: { route: string }) {
  const reduced = useReducedMotion();
  const access = useAccess();
  const scope = useScope();
  const required = [...navigation]
    .sort((a, b) => b.href.length - a.href.length)
    .find(
      (n) => route === n.href || route.startsWith(n.href + "/"),
    )?.permission;
  if (required && !access.data?.permissions.includes(required))
    return (
      <Empty title="Access restricted">
        Your firm role does not grant this workspace. Contact your
        administrator.
      </Empty>
    );
  let page: React.ReactNode;
  switch (route) {
    case "/client-collaboration":
      page = <ClientCollaboration />;
      break;
    case "/compliance/country":
      page = <CountryCompliance />;
      break;
    case "/reports/statutory":
      page = <StatutoryReportBuilder />;
      break;
    case "/audit/india/statutory":
      page = <StatutoryPractice area="companies-act" />;
      break;
    case "/audit/india/caro":
      page = <StatutoryPractice area="caro" />;
      break;
    case "/audit/india/tax-audit":
      page = <StatutoryPractice area="india-tax-audit" />;
      break;
    case "/audit/india/financial-reporting":
      page = <IndiaFinancialReporting />;
      break;
    case "/audit/india/disclosures":
      page = <StatutoryPractice area="india-disclosures" />;
      break;
    case "/settings/regulatory-rules":
      page = <RegulatoryLibrary />;
      break;
    case "/settings":
    case "/settings/countries":
      page = <CountrySettings />;
      break;
    case "/modules":
      page = <ModuleDirectory />;
      break;
    case "/groups":
      page = <GroupWorkspace />;
      break;
    case "/working-papers":
      page = <RecordHub kind="working-papers" />;
      break;
    case "/findings":
      page = <RecordHub kind="findings" />;
      break;
    case "/dashboard":
      page = <Dashboard />;
      break;
    case "/clients":
      page = <Clients />;
      break;
    case "/integrations":
      page = <Integrations />;
      break;
    case "/integrations/zoho/callback":
      page = <ZohoCallback />;
      break;
    case "/financials/trial-balance":
      page = <TrialBalance />;
      break;
    case "/financials/general-ledger":
      page = <Ledger />;
      break;
    case "/financials/journals":
      page = <Ledger journals />;
      break;
    case "/financials/mapping":
      page = <Mapping />;
      break;
    case "/financials/reconciliation":
      page = <Reconciliation />;
      break;
    case "/audit/risk-intelligence":
    case "/audit/analytics":
    case "/audit/journal-testing":
      page = <Analytics />;
      break;
    case "/audit/sampling":
      page = <Sampling />;
      break;
    case "/ai-copilot":
      page = <Copilot />;
      break;
    case "/compliance":
      page = <Compliance />;
      break;
    case "/tax":
      page = <TaxStudio />;
      break;
    case "/vat":
      page = <VATStudio />;
      break;
    case "/engagements":
      page = <Engagements />;
      break;
    case "/evidence":
    case "/reports":
    case "/settings":
      page = <Supporting route={route} />;
      break;
    default:
      page =
        route === "/intelligence" || route.startsWith("/intelligence/") ? (
          <AccountingIntelligence
            eid={route.split("/")[2]}
            area={route.split("/")[3]}
          />
        ) : route === "/board" ? (
          <BoardPortal />
        ) : route === "/grc" || route.startsWith("/grc/") ? (
          <GRCStudio eid={route.split("/")[2]} area={route.split("/")[3]} />
        ) : route.startsWith("/ai-lab") ? (
          <Phase9Studio mode="ml" area={route.split("/")[2]} />
        ) : route.startsWith("/pillar-two") ? (
          <Phase9Studio mode="dmtt" area={route.split("/")[2]} />
        ) : route.startsWith("/ai/") ? (
          <EnterpriseAI area={route.split("/")[2]} />
        ) : route === "/tp" || route.startsWith("/tp/") ? (
          <TPStudio
            key={route}
            id={route.split("/")[2]}
            area={route.split("/")[3]}
          />
        ) : route.startsWith("/vat/") ? (
          <VATStudio
            key={route}
            id={route.split("/")[2]}
            area={route.split("/")[3]}
          />
        ) : route.startsWith("/tax/") ? (
          <TaxStudio
            key={route}
            id={route.split("/")[2]}
            area={route.split("/")[3]}
          />
        ) : route === "/ifrs" || route.startsWith("/ifrs/") ? (
          <IFRSStudio
            key={route}
            id={route.split("/")[2]}
            area={route.split("/")[3]}
          />
        ) : route.startsWith("/admin/") ? (
          <AuditAdministration area={route.split("/")[2]} />
        ) : route === "/client-portal" ? (
          <ClientPortal />
        ) : route.startsWith("/engagements/") &&
          route.split("/")[3] === "workspace" ? (
          <EngagementWorkspace eid={route.split("/")[2]} />
        ) : route.startsWith("/engagements/") &&
          route.split("/")[3] === "lifecycle" ? (
          <WorkingPaperGraph eid={route.split("/")[2]} lifecycle />
        ) : route.startsWith("/engagements/") &&
          route.split("/")[3] === "graph" ? (
          <WorkingPaperGraph eid={route.split("/")[2]} />
        ) : route.startsWith("/engagements/") && route.split("/").length > 3 ? (
          <AuditStudio
            key={route}
            id={route.split("/")[2]}
            area={route.split("/")[3]}
          />
        ) : route.startsWith("/engagements/") ? (
          <Engagements id={route.split("/")[2]} />
        ) : (
          <Empty title="Page not found">
            Choose a workspace from the navigation.
          </Empty>
        );
  }
  return (
    <motion.div
      className={
        route.startsWith("/ifrs") ||
        route.startsWith("/tax") ||
        route.startsWith("/vat") ||
        route.startsWith("/tp") ||
        route.startsWith("/ai-lab") ||
        route.startsWith("/pillar-two") ||
        route.startsWith("/grc") ||
        route.startsWith("/board")
          ? "route-content ifrs-route" +
            (route.startsWith("/tp") ? " tp-route" : "")
          : "route-content"
      }
      key={[route, scope.tenant, scope.client, scope.entity, scope.period].join(
        ":",
      )}
      initial={reduced ? false : { opacity: 0.7 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.12 }}
    >
      {page}
    </motion.div>
  );
}
