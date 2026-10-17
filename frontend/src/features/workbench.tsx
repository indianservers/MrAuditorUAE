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
export function Workbench({ route }: { route: string }) {
  const reduced = useReducedMotion();
  const access = useAccess();
  const scope = useScope();
  const required = navigation.find(
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
      page = <Compliance tax />;
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
      page = route.startsWith("/engagements/") ? (
        <Engagements id={route.split("/")[2]} />
      ) : (
        <Empty title="Page not found">
          Choose a workspace from the navigation.
        </Empty>
      );
  }
  return (
    <motion.div
      className="route-content"
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
