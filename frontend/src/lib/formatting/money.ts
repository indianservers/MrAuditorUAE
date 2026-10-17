// String-only formatting preserves NUMERIC(28,8). Never converts balances to float.
export function money(value: unknown, precision = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  let raw = String(value);
  const scientific = raw.match(/^(-?)(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/);
  if (scientific) {
    const exponent = Number(scientific[4]);
    if (Math.abs(exponent) > 30) return "—";
    const digits = scientific[2] + (scientific[3] || "");
    const point = scientific[2].length + exponent;
    raw =
      scientific[1] +
      (point <= 0
        ? "0." + "0".repeat(-point) + digits
        : point >= digits.length
          ? digits + "0".repeat(point - digits.length)
          : digits.slice(0, point) + "." + digits.slice(point));
  }
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return "—";
  const negative = raw.startsWith("-");
  const [whole, fraction = ""] = raw.replace("-", "").split(".");
  const text =
    whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
    (precision
      ? "." + fraction.padEnd(precision, "0").slice(0, precision)
      : "");
  return negative ? "(" + text + ")" : text;
}
export const textValue = (v: unknown) =>
  v === null || v === undefined
    ? "—"
    : typeof v === "object"
      ? JSON.stringify(v)
      : String(v);
export function csvCell(v: unknown) {
  let t = textValue(v);
  if (/^[=+\-@]/.test(t.trimStart()) || /^[\t\r\n]/.test(t)) t = "'" + t;
  return '"' + t.replaceAll('"', '""') + '"';
}
export function downloadCSV(name: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const blob = new Blob(
    [
      "\uFEFF" +
        [
          keys.map(csvCell).join(","),
          ...rows.map((r) => keys.map((k) => csvCell(r[k])).join(",")),
        ].join("\r\n"),
    ],
    { type: "text/csv;charset=utf-8" },
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
