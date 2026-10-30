"use client";
import { useState } from "react";
import { Button, ErrorState } from "@/components/ui/primitives";
import { useAction } from "@/hooks/use-api";

export type Schema = {
  type?: string;
  title?: string;
  format?: string;
  default?: unknown;
  enum?: unknown[];
  const?: unknown;
  $ref?: string;
  anyOf?: Schema[];
  properties?: Record<string, Schema>;
  items?: Schema;
  required?: string[];
  $defs?: Record<string, Schema>;
  additionalProperties?: Schema | boolean;
  minLength?: number;
  maxLength?: number;
};
export function label(key: string) {
  return key
    .replace(/_ids?$/, "")
    .replaceAll("_", " ")
    .replace(/^./, (x) => x.toUpperCase());
}
function resolved(schema: Schema, root: Schema): Schema {
  if (schema.$ref)
    return root.$defs?.[schema.$ref.split("/").at(-1)!] || schema;
  if (schema.anyOf)
    return resolved(
      schema.anyOf.find((x) => x.type !== "null") || schema.anyOf[0],
      root,
    );
  return schema;
}
export function initial(schema: Schema, root = schema): unknown {
  if (schema.default !== undefined) return schema.default;
  const s = resolved(schema, root);
  if (s.const !== undefined) return s.const;
  if (s.enum) return "";
  if (s.type === "object")
    return Object.fromEntries(
      (s.required || []).map((k) => [
        k,
        initial(s.properties?.[k] || {}, root),
      ]),
    );
  if (s.type === "array") return [];
  if (s.type === "boolean") return false;
  return "";
}
export function Field({
  name,
  schema,
  root,
  value,
  change,
  depth = 0,
}: {
  name: string;
  schema: Schema;
  root: Schema;
  value: unknown;
  change: (value: unknown) => void;
  depth?: number;
}) {
  const s = resolved(schema, root);
  if (depth > 8)
    return <p>Nested content exceeds the interactive editor limit.</p>;
  if (s.type === "object") {
    const values = (value || {}) as Record<string, unknown>;
    if (!s.properties)
      return (
        <Dictionary
          name={name}
          schema={s}
          root={root}
          value={values}
          change={change}
          depth={depth}
        />
      );
    return (
      <fieldset className="grc-fields">
        <legend>{label(name)}</legend>
        {Object.entries(s.properties).map(([key, child]) => (
          <div key={key}>
            <Field
              name={key}
              schema={child}
              root={root}
              value={values[key]}
              depth={depth + 1}
              change={(v) => {
                const next =
                  value == null
                    ? { ...(initial(s, root) as Record<string, unknown>) }
                    : { ...values };
                if (v === undefined) delete next[key];
                else next[key] = v;
                change(next);
              }}
            />
            {!s.required?.includes(key) && values[key] !== undefined && (
              <button
                className="grc-clear"
                type="button"
                onClick={() => {
                  const next = { ...values };
                  delete next[key];
                  change(next);
                }}
              >
                Clear optional field
              </button>
            )}
          </div>
        ))}
      </fieldset>
    );
  }
  if (s.type === "array") {
    const rows = Array.isArray(value) ? value : [];
    return (
      <fieldset>
        <legend>{label(name)}</legend>
        {rows.map((item, i) => (
          <div className="grc-repeat" key={i}>
            <Field
              name={`${name} ${i + 1}`}
              schema={s.items || {}}
              root={root}
              value={item}
              depth={depth + 1}
              change={(v) =>
                change(rows.map((x, index) => (index === i ? v : x)))
              }
            />
            <Button
              type="button"
              onClick={() => change(rows.filter((_, index) => index !== i))}
            >
              Remove item {i + 1}
            </Button>
          </div>
        ))}
        <Button
          type="button"
          onClick={() => change([...rows, initial(s.items || {}, root)])}
        >
          Add {label(name)}
        </Button>
      </fieldset>
    );
  }
  if (s.const !== undefined)
    return (
      <label>
        {label(name)}
        <output>{String(value ?? s.const)}</output>
      </label>
    );
  if (s.type === "boolean")
    return (
      <label className="grc-check">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => change(e.target.checked)}
        />
        {label(name)}
      </label>
    );
  if (s.enum)
    return (
      <label>
        {label(name)}
        <select
          value={String(value ?? "")}
          onChange={(e) =>
            change(
              s.enum?.find((x) => String(x) === e.target.value) ??
                e.target.value,
            )
          }
        >
          <option value="">Select</option>
          {s.enum.map((x) => (
            <option key={String(x)} value={String(x)}>
              {label(String(x))}
            </option>
          ))}
        </select>
      </label>
    );
  const props = {
    value: String(value ?? ""),
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      change(e.target.value),
  };
  if ((s.maxLength || 0) >= 1000)
    return (
      <label>
        {label(name)}
        <textarea {...props} rows={4} maxLength={s.maxLength} />
      </label>
    );
  return (
    <label>
      {label(name)}
      <input
        {...props}
        type={
          s.format === "date"
            ? "date"
            : s.format === "date-time"
              ? "datetime-local"
              : "text"
        }
        inputMode={
          s.type === "integer" || s.type === "number" ? "decimal" : undefined
        }
        maxLength={s.maxLength}
        placeholder={
          s.format === "uuid"
            ? "Select or paste an authorized source reference"
            : undefined
        }
      />
    </label>
  );
}
function Dictionary({
  name,
  schema,
  root,
  value,
  change,
  depth,
}: {
  name: string;
  schema: Schema;
  root: Schema;
  value: Record<string, unknown>;
  change: (v: unknown) => void;
  depth: number;
}) {
  const [key, setKey] = useState("");
  const child =
    typeof schema.additionalProperties === "object"
      ? schema.additionalProperties
      : { type: "string" };
  return (
    <fieldset>
      <legend>{label(name)}</legend>
      {Object.entries(value).map(([k, v]) => (
        <div key={k} className="grc-repeat">
          <Field
            name={k}
            schema={child}
            root={root}
            value={v}
            depth={depth + 1}
            change={(x) => change({ ...value, [k]: x })}
          />
          <Button
            type="button"
            onClick={() => {
              const next = { ...value };
              delete next[k];
              change(next);
            }}
          >
            Remove {k}
          </Button>
        </div>
      ))}
      <div className="grc-toolbar">
        <input
          aria-label={`${label(name)} new key`}
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="Criterion or mapping name"
        />
        <Button
          type="button"
          aria-label={`Add ${label(name)} entry`}
          disabled={!key || key in value}
          onClick={() => {
            change({ ...value, [key]: initial(child, root) });
            setKey("");
          }}
        >
          Add entry
        </Button>
      </div>
    </fieldset>
  );
}
export type Paper = {
  id: string;
  reference: string;
  title: string;
  kind: string;
  version: number;
  status: string;
  body: Record<string, unknown>;
  [key: string]: unknown;
};
export function PaperEditor({
  base,
  kind,
  schema,
  paper,
  done,
}: {
  base: string;
  kind: string;
  schema: Schema;
  paper?: Paper;
  done: () => void;
}) {
  const action = useAction<Paper>();
  const [title, setTitle] = useState(paper?.title || "");
  const [reference, setReference] = useState(paper?.reference || "");
  const [body, setBody] = useState<unknown>(() =>
    paper
      ? Object.fromEntries(
          Object.entries(paper.body).filter(
            ([k]) =>
              !["review_stage", "review_cycle", "review_approvers"].includes(k),
          ),
        )
      : initial(schema),
  );
  return (
    <form
      className="grc-editor"
      onSubmit={async (e) => {
        e.preventDefault();
        await action
          .mutateAsync({
            path: `${base}/records/${paper?.id || kind}`,
            method: paper ? "PATCH" : "POST",
            body: {
              title,
              reference,
              body,
              ...(paper ? { version: paper.version } : {}),
            },
          })
          .then(done)
          .catch(() => {});
      }}
    >
      <div className="grc-toolbar">
        <h2>{paper ? "Revise workpaper" : "Prepare workpaper"}</h2>
        <Button type="button" onClick={done}>
          Close editor
        </Button>
      </div>
      <label>
        Reference
        <input
          required
          value={reference}
          onChange={(e) => setReference(e.target.value)}
        />
      </label>
      <label>
        Title
        <input
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <Field
        name={kind}
        schema={schema}
        root={schema}
        value={body}
        change={setBody}
      />
      {action.error && <ErrorState error={action.error} />}
      <Button primary disabled={action.isPending}>
        Save draft
      </Button>
    </form>
  );
}
