/** Reporting currencies are distinct from original invoice/account currencies. */
export function reportingCurrency(
  workflow: string,
  country?: string,
): string | null {
  if (
    [
      "india-esic-population",
      "india-document-series",
      "india-gstr1-documents",
      "india-gstr1-summary",
      "india-payroll-basis-proration",
      "india-establishment-charges",
      "india-payroll-rules",
      "india-gst",
      "india-withholding",
      "india-withholding-liability",
      "india-withholding-credit",
    ].includes(workflow)
  )
    return "INR";
  if (
    [
      "uae-pension-review",
      "uae-savings-review",
      "uae-vat",
      "uae-vat-return",
    ].includes(workflow)
  )
    return "AED";
  if (workflow === "tax-turnover-bridge")
    return country === "IN" ? "INR" : country === "AE" ? "AED" : null;
  return null;
}

export function draftCurrency(config?: {
  country: string;
  default_currency?: string | null;
}): string {
  if (config && "default_currency" in config)
    return config.default_currency || "";
  // Compatibility with metadata from older servers; no default for unconfigured countries.
  return config?.country === "IN"
    ? "INR"
    : config?.country === "AE"
      ? "AED"
      : "";
}
