"use client";

import { useEffect, useRef, useState } from "react";

type Column = { left: string; right: string };
type Box = Column & { top: string; bottom: string };
type GridPage = {
  page: string;
  top: string;
  row_height: string;
  row_count: string;
  account_header: Box;
  currency_header: Box;
};
const fields = [
  "date",
  "reference",
  "amount",
  "debit",
  "credit",
  "counterparty",
  "currency",
  "account_code",
] as const;
type Field = (typeof fields)[number];
export type PDFGridDraft = {
  account: string;
  currency: string;
  scope_assessment: string;
  amount_basis: "" | "signed" | "debit-positive" | "credit-positive";
  columns: Record<Field, Column>;
  pages: GridPage[];
  ignored_columns: Column[];
};
const emptyBox = (): Box => ({ left: "", right: "", top: "", bottom: "" });
export const emptyPDFGrid = (): PDFGridDraft => ({
  account: "",
  currency: "",
  scope_assessment: "",
  amount_basis: "",
  columns: Object.fromEntries(
    fields.map((field) => [field, { left: "", right: "" }]),
  ) as Record<Field, Column>,
  pages: [
    {
      page: "1",
      top: "",
      row_height: "",
      row_count: "",
      account_header: emptyBox(),
      currency_header: emptyBox(),
    },
  ],
  ignored_columns: [],
});

export function buildPDFGrid(draft: PDFGridDraft) {
  const number = (value: string, label: string, maximum = 100) => {
    const result = Number(value);
    if (
      !value.trim() ||
      !Number.isFinite(result) ||
      result < 0 ||
      result > maximum
    )
      throw new Error(`Enter a valid ${label}.`);
    return result;
  };
  const column = (value: Column, label: string) => {
    const left = number(value.left, `${label} left boundary`),
      right = number(value.right, `${label} right boundary`);
    if (left >= right) throw new Error(`${label}: left must precede right.`);
    return { left, right };
  };
  const box = (value: Box, label: string) => {
    const top = number(value.top, `${label} top`),
      bottom = number(value.bottom, `${label} bottom`);
    if (top >= bottom) throw new Error(`${label}: top must precede bottom.`);
    return { ...column(value, label), top, bottom };
  };
  if (
    !draft.account.trim() ||
    !/^[A-Z]{3}$/.test(draft.currency.trim().toUpperCase())
  )
    throw new Error(
      "Enter the exact PDF account header and a three-letter currency.",
    );
  if (!draft.amount_basis || draft.scope_assessment.trim().length < 10)
    throw new Error(
      "Choose the PDF amount convention and assess the selected population and ignored columns.",
    );
  const required: Field[] = [
    "date",
    "reference",
    ...(draft.amount_basis === "signed"
      ? ["amount" as const]
      : ["debit" as const, "credit" as const]),
  ];
  const optional: Field[] = ["counterparty", "currency", "account_code"];
  const selected = [
    ...required,
    ...optional.filter(
      (field) => draft.columns[field].left || draft.columns[field].right,
    ),
  ];
  const columns = Object.fromEntries(
    selected.map((field) => [
      field,
      column(draft.columns[field], `PDF ${field}`),
    ]),
  );
  const ignored_columns = draft.ignored_columns.map((value, index) =>
    column(value, `Ignored PDF column ${index + 1}`),
  );
  const intervals = [...Object.values(columns), ...ignored_columns].sort(
    (a, b) => a.left - b.left,
  );
  if (
    intervals.some(
      (value, index) => index > 0 && intervals[index - 1].right > value.left,
    )
  )
    throw new Error("Mapped and ignored PDF columns must not overlap.");
  const pages = draft.pages.map((page, index) => {
    const pageNumber = number(page.page, "PDF page number", 20);
    const row_count = number(page.row_count, "PDF row count", 5000);
    const top = number(page.top, "PDF row-grid top"),
      row_height = number(page.row_height, "PDF row height");
    if (
      !Number.isInteger(pageNumber) ||
      pageNumber < 1 ||
      !Number.isInteger(row_count) ||
      row_count < 1 ||
      row_height <= 0 ||
      top + row_height * row_count > 100
    )
      throw new Error(
        `PDF page ${index + 1}: check the page number, row count and grid bounds.`,
      );
    return {
      page: pageNumber,
      top,
      row_height,
      row_count,
      account_header: box(
        page.account_header,
        `PDF page ${index + 1} account header`,
      ),
      currency_header: box(
        page.currency_header,
        `PDF page ${index + 1} currency header`,
      ),
    };
  });
  if (
    new Set(pages.map((page) => page.page)).size !== pages.length ||
    pages.reduce((total, page) => total + page.row_count, 0) > 5000
  )
    throw new Error(
      "Select each PDF page once, with at most 5,000 row bands in total.",
    );
  return {
    account: draft.account.trim(),
    currency: draft.currency.trim().toUpperCase(),
    amount_basis: draft.amount_basis,
    scope_assessment: draft.scope_assessment.trim(),
    columns,
    pages,
    ignored_columns,
  };
}

export function PDFGridEditor({
  draft,
  onChange,
  eid,
  evidence,
  tenant,
}: {
  draft: PDFGridDraft;
  onChange: (value: PDFGridDraft) => void;
  eid: string;
  evidence: string;
  tenant: string;
}) {
  const [preview, setPreview] = useState("");
  const [previewPage, setPreviewPage] = useState("1");
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const previewURL = useRef("");
  useEffect(
    () => () => {
      controller.current?.abort();
      if (previewURL.current) URL.revokeObjectURL(previewURL.current);
    },
    [],
  );
  const numeric = (
    label: string,
    value: string,
    update: (value: string) => void,
  ) => (
    <label key={label}>
      {label}
      <input
        type="number"
        step="any"
        min="0"
        value={value}
        onChange={(event) => update(event.target.value)}
      />
    </label>
  );
  const active: Field[] = [
    "date",
    "reference",
    ...(draft.amount_basis === "signed"
      ? ["amount" as const]
      : draft.amount_basis
        ? ["debit" as const, "credit" as const]
        : []),
    "counterparty",
    "currency",
    "account_code",
  ];
  const updatePage = (index: number, value: GridPage) =>
    onChange({
      ...draft,
      pages: draft.pages.map((page, position) =>
        position === index ? value : page,
      ),
    });
  async function showPreview() {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/backend/intelligence/engagements/${encodeURIComponent(eid)}/evidence/${encodeURIComponent(evidence)}/preview?page=${encodeURIComponent(previewPage)}`,
        { headers: { "X-Tenant-ID": tenant }, signal: request.signal },
      );
      if (
        !response.ok ||
        !response.headers.get("content-type")?.includes("image/png")
      )
        throw new Error("PDF preview unavailable for this evidence and page.");
      const blob = await response.blob();
      if (!request.signal.aborted) {
        if (previewURL.current) URL.revokeObjectURL(previewURL.current);
        previewURL.current = URL.createObjectURL(blob);
        setPreview(previewURL.current);
      }
    } catch (cause) {
      if (!request.signal.aborted) setError((cause as Error).message);
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }
  return (
    <section
      style={{ flexBasis: "100%", width: "100%" }}
      aria-label="PDF text-grid mapping"
    >
      <h3>Map the retained PDF text table</h3>
      <p>
        Coordinates are percentages from the top left. Map the account and
        currency header values on every selected page, then the first data-row
        top, row height and complete row count. Column bands apply across all
        pages. Text that crosses a boundary or an undeclared column is rejected.
        Image-only/OCR and variable-height or wrapped rows require a separately
        qualified profile.
      </p>
      <div className="toolbar" style={{ flexWrap: "wrap" }}>
        <label>
          PDF account header
          <input
            value={draft.account}
            maxLength={120}
            onChange={(event) =>
              onChange({ ...draft, account: event.target.value })
            }
          />
        </label>
        <label>
          PDF statement currency
          <input
            value={draft.currency}
            maxLength={3}
            onChange={(event) =>
              onChange({ ...draft, currency: event.target.value })
            }
          />
        </label>
        <label>
          PDF amount convention
          <select
            value={draft.amount_basis}
            onChange={(event) =>
              onChange({
                ...draft,
                amount_basis: event.target
                  .value as PDFGridDraft["amount_basis"],
              })
            }
          >
            <option value="">Select the statement convention</option>
            <option value="signed">Signed amount column</option>
            <option value="debit-positive">Debit minus credit</option>
            <option value="credit-positive">Credit minus debit</option>
          </select>
        </label>
      </div>
      <div className="toolbar" style={{ flexWrap: "wrap" }}>
        {numeric("Preview PDF page", previewPage, setPreviewPage)}
        <button
          type="button"
          className="button"
          disabled={!evidence || busy}
          onClick={showPreview}
        >
          Show retained PDF preview
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {preview && (
        <figure style={{ maxWidth: 720 }}>
          {/* Authenticated short-lived raster blob; it is not a public image URL. */}
          <img
            src={preview}
            alt="Raster preview of the retained PDF page"
            style={{ width: "100%", height: "auto" }}
            onMouseMove={(event) => {
              const rect = event.currentTarget.getBoundingClientRect();
              if (rect.width && rect.height)
                setPoint({
                  x: ((event.clientX - rect.left) / rect.width) * 100,
                  y: ((event.clientY - rect.top) / rect.height) * 100,
                });
            }}
          />
          <figcaption>
            {point
              ? `Pointer: x ${point.x.toFixed(2)}%, y ${point.y.toFixed(2)}% from top left.`
              : "Move over the raster preview to read percentage coordinates."}{" "}
            The original document remains retained unchanged.
          </figcaption>
        </figure>
      )}
      <fieldset>
        <legend>PDF column boundaries</legend>
        {active.map((field) => (
          <div className="toolbar" key={field}>
            {numeric(
              `PDF ${field} column left (%)`,
              draft.columns[field].left,
              (value) =>
                onChange({
                  ...draft,
                  columns: {
                    ...draft.columns,
                    [field]: { ...draft.columns[field], left: value },
                  },
                }),
            )}
            {numeric(
              `PDF ${field} column right (%)`,
              draft.columns[field].right,
              (value) =>
                onChange({
                  ...draft,
                  columns: {
                    ...draft.columns,
                    [field]: { ...draft.columns[field], right: value },
                  },
                }),
            )}
          </div>
        ))}
        <p>
          Counterparty, row currency and row account columns are optional. If
          mapped, currency/account values must agree with the verified page
          headers.
        </p>
        {draft.ignored_columns.map((column, index) => (
          <div className="toolbar" key={index}>
            {numeric(
              `PDF ignored column ${index + 1} left (%)`,
              column.left,
              (value) =>
                onChange({
                  ...draft,
                  ignored_columns: draft.ignored_columns.map(
                    (item, position) =>
                      position === index ? { ...item, left: value } : item,
                  ),
                }),
            )}
            {numeric(
              `PDF ignored column ${index + 1} right (%)`,
              column.right,
              (value) =>
                onChange({
                  ...draft,
                  ignored_columns: draft.ignored_columns.map(
                    (item, position) =>
                      position === index ? { ...item, right: value } : item,
                  ),
                }),
            )}
            <button
              type="button"
              className="button"
              onClick={() =>
                onChange({
                  ...draft,
                  ignored_columns: draft.ignored_columns.filter(
                    (_, position) => position !== index,
                  ),
                })
              }
            >
              Remove ignored column {index + 1}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="button"
          disabled={draft.ignored_columns.length >= 12}
          onClick={() =>
            onChange({
              ...draft,
              ignored_columns: [
                ...draft.ignored_columns,
                { left: "", right: "" },
              ],
            })
          }
        >
          Add explicitly ignored PDF column
        </button>
      </fieldset>
      {draft.pages.map((page, index) => (
        <fieldset key={index}>
          <legend>PDF grid {index + 1}</legend>
          <div className="toolbar" style={{ flexWrap: "wrap" }}>
            {(["page", "top", "row_height", "row_count"] as const).map(
              (field) =>
                numeric(
                  `PDF grid ${index + 1} ${field.replaceAll("_", " ")}`,
                  page[field],
                  (value) => updatePage(index, { ...page, [field]: value }),
                ),
            )}
            {(["account_header", "currency_header"] as const).map((header) => (
              <fieldset key={header}>
                <legend>{header.replaceAll("_", " ")} value box (%)</legend>
                {(["left", "right", "top", "bottom"] as const).map((field) =>
                  numeric(
                    `PDF grid ${index + 1} ${header.replaceAll("_", " ")} ${field} (%)`,
                    page[header][field],
                    (value) =>
                      updatePage(index, {
                        ...page,
                        [header]: { ...page[header], [field]: value },
                      }),
                  ),
                )}
              </fieldset>
            ))}
            {draft.pages.length > 1 && (
              <button
                type="button"
                className="button"
                onClick={() =>
                  onChange({
                    ...draft,
                    pages: draft.pages.filter(
                      (_, position) => position !== index,
                    ),
                  })
                }
              >
                Remove PDF grid {index + 1}
              </button>
            )}
          </div>
        </fieldset>
      ))}
      <button
        type="button"
        className="button"
        disabled={draft.pages.length >= 20}
        onClick={() =>
          onChange({
            ...draft,
            pages: [
              ...draft.pages,
              {
                ...structuredClone(draft.pages[draft.pages.length - 1]),
                page: String(
                  Number(draft.pages[draft.pages.length - 1].page) + 1,
                ),
              },
            ],
          })
        }
      >
        Add PDF page with the same layout
      </button>
      <label>
        PDF scope and excluded-column assessment
        <textarea
          value={draft.scope_assessment}
          maxLength={2000}
          onChange={(event) =>
            onChange({ ...draft, scope_assessment: event.target.value })
          }
        />
      </label>
    </section>
  );
}
