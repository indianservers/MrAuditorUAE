import { describe, it, expect } from "vitest";
import { money, csvCell } from "@/lib/formatting/money";
import { qs } from "@/lib/api/client";
describe("financial presentation without float calculations", () => {
  it("preserves large NUMERIC whole digits", () =>
    expect(money("99999999999999999999.12000000")).toBe(
      "99,999,999,999,999,999,999.12",
    ));
  it("formats negatives and explicit precision", () => {
    expect(money("-90.10000000")).toBe("(90.10)");
    expect(money("12.345", 3)).toBe("12.345");
    expect(money("0", 0)).toBe("0");
  });
  it("does not invent missing values", () => {
    expect(money(null)).toBe("—");
    expect(money("NaN")).toBe("—");
    expect(money("0E-8")).toBe("0.00");
    expect(money("1E-8", 8)).toBe("0.00000001");
  });
  it("neutralizes spreadsheet formula injection", () => {
    for (const value of ["=1+1", "+cmd", "-cmd", "@sum", "\tformula"])
      expect(csvCell(value)).toMatch(/^"'/);
    expect(csvCell('a"b')).toBe('"a""b"');
  });
  it("encodes filters without losing zero", () =>
    expect(qs({ offset: 0, search: "A&B", missing: undefined })).toBe(
      "offset=0&search=A%26B",
    ));
});
