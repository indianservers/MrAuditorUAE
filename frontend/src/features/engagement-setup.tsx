"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight,
  ArrowLeft,
  Building2,
  Check,
  ShieldCheck,
} from "lucide-react";
import { Modal, Button, ErrorState } from "@/components/ui/primitives";
import { useAPI, useAction } from "@/hooks/use-api";
import type { Entity, Period, Engagement, Page } from "@/types/models";
export function EngagementSetup({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [search, setSearch] = useState("");
  const [entity, setEntity] = useState("");
  const [period, setPeriod] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState("External Audit");
  const entities = useAPI<Page<Entity>>(
    `entities?limit=100&search=${encodeURIComponent(search)}`,
    open,
  );
  const periods = useAPI<Page<Period>>(
    `workspace/directory?entity_id=${entity}&limit=100`,
    open && !!entity,
  );
  const action = useAction<Engagement>();
  const selected = entities.data?.items.find((e) => e.id === entity);
  const selectedPeriod = periods.data?.items.find((p) => p.id === period);
  const valid =
    step === 0
      ? !!selected
      : step === 1
        ? !!selectedPeriod && name.trim().length >= 3
        : true;
  return (
    <Modal
      open={open}
      onOpenChange={(v) => {
        if (!v && !action.isPending) onClose();
      }}
      title="New audit engagement"
      wide
    >
      <div className="engagement-setup">
        <ol className="setup-steps" aria-label="Engagement setup steps">
          {["Legal entity", "Period & scope", "Review & create"].map(
            (label, i) => (
              <li key={label} aria-current={step === i ? "step" : undefined}>
                <span>{i < step ? <Check size={14} /> : i + 1}</span>
                {label}
              </li>
            ),
          )}
        </ol>
        <ErrorState error={entities.error || periods.error || action.error} />
        {step === 0 ? (
          <section>
            <span className="eyebrow">01 / YOUR CLIENT</span>
            <h2>Start with the right entity</h2>
            <p>
              Search your firm’s saved legal entities. Registration details
              remain subject to source verification.
            </p>
            <label>
              Find a legal entity
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by company name…"
              />
            </label>
            <label>
              Legal entity
              <select
                aria-label="Legal entity"
                value={entity}
                onChange={(e) => {
                  setEntity(e.target.value);
                  setPeriod("");
                  const item = entities.data?.items.find(
                    (x) => x.id === e.target.value,
                  );
                  if (item) setName(`${item.name} — ${kind}`);
                }}
              >
                <option value="">Select a saved entity</option>
                {entities.data?.items.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name} · {e.country}
                  </option>
                ))}
              </select>
            </label>
            {selected && (
              <div className="setup-entity">
                <Building2 size={25} />
                <div>
                  <strong>{selected.name}</strong>
                  <p>
                    {selected.country} · {selected.functional_currency} · Saved
                    firm record
                  </p>
                </div>
              </div>
            )}
            <p>
              Need a new entity?{" "}
              <Link href="/clients">Create it in the client register</Link>. No
              external company lookup is implied.
            </p>
          </section>
        ) : step === 1 ? (
          <section>
            <span className="eyebrow">02 / DEFINE YOUR SCOPE</span>
            <h2>Choose the period under review</h2>
            <label>
              Engagement name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={200}
              />
            </label>
            <label>
              Engagement type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {[
                  "External Audit",
                  "Internal Audit",
                  "IFRS Review",
                  "Corporate Tax",
                  "VAT",
                  "Transfer Pricing",
                  "Pillar Two",
                  "General Compliance",
                ].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Financial period
              <select
                aria-label="Financial period"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
              >
                <option value="">Select financial period</option>
                {periods.data?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.start_date} — {p.end_date}
                  </option>
                ))}
              </select>
            </label>
            {!periods.isLoading && !periods.data?.items.length && (
              <p>
                Create a financial period in the entity’s client details before
                continuing.
              </p>
            )}
            <div className="setup-assurance">
              <ShieldCheck size={20} />
              <p>
                Reporting country and accounting framework are reviewed
                separately in the engagement workspace. Creating an engagement
                does not approve its legal applicability.
              </p>
            </div>
          </section>
        ) : (
          <section>
            <span className="eyebrow">03 / READY TO BEGIN</span>
            <h2>A connected audit starts here</h2>
            <dl className="setup-summary">
              <dt>Legal entity</dt>
              <dd>{selected?.name}</dd>
              <dt>Engagement</dt>
              <dd>{name}</dd>
              <dt>Scope</dt>
              <dd>{kind}</dd>
              <dt>Reporting period</dt>
              <dd>
                {selectedPeriod?.start_date} — {selectedPeriod?.end_date}
              </dd>
            </dl>
            <div className="setup-assurance">
              <ShieldCheck size={20} />
              <p>
                Next: review the reporting context, assign your team, connect
                accounting sources and resolve the readiness blockers. All
                conclusions follow independent approval.
              </p>
            </div>
          </section>
        )}
        <footer>
          <span>Step {step + 1} of 3</span>
          <div>
            {step > 0 && (
              <Button
                disabled={action.isPending}
                onClick={() => setStep(step - 1)}
              >
                <ArrowLeft size={15} /> Back
              </Button>
            )}
            {step < 2 ? (
              <Button
                primary
                disabled={!valid}
                onClick={() => setStep(step + 1)}
              >
                Continue <ArrowRight size={15} />
              </Button>
            ) : (
              <Button
                primary
                disabled={action.isPending || !entity || !period}
                onClick={async () => {
                  const created = await action
                    .mutateAsync({
                      path: "engagements",
                      body: {
                        entity_id: entity,
                        period_id: period,
                        name: name.trim(),
                        engagement_type: kind,
                      },
                    })
                    .catch(() => null);
                  if (created) {
                    onClose();
                    router.push(`/engagements/${created.id}/workspace`);
                  }
                }}
              >
                {action.isPending ? "Creating…" : "Create engagement"}
                <ArrowRight size={15} />
              </Button>
            )}
          </div>
        </footer>
      </div>
    </Modal>
  );
}
