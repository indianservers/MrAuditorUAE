"use client";

type Row = Record<string, unknown>;
export function BankAccountEvidenceReview({ rows }: { rows: Row[] }) {
  const roles = ["register", "ledger", "bank"];
  const fields = [
    "account",
    "bank_country",
    "account_scheme",
    "account_number",
    "routing_code",
    "currency",
    "owner_country",
    "owner_name",
    "owner_identifier_scheme",
    "owner_identifier",
    "valid_from",
    "valid_through",
    "assertion_status",
    "exceptions",
    "state",
    "evidence_reference",
  ];
  const text = (value: unknown) =>
    Array.isArray(value)
      ? value.length
        ? value
            .map((item) => String(item).replaceAll("_", " ").toLowerCase())
            .join(", ")
        : "None"
      : String(value ?? "Not retained");
  return (
    <section aria-label="Bank account evidence comparison">
      <h3>Bank account and owner evidence</h3>
      <p>
        Compare the approved register, ledger setup and retained bank evidence
        side by side. An asserted confirmation and a valid identifier format do
        not authenticate a bank account or establish payment authority.
      </p>
      <div className="table-wrap">
        <table aria-label="Bank account identity observations">
          <thead>
            <tr>
              <th scope="col">Evidence field</th>
              {roles.map((role) => (
                <th scope="col" key={role}>
                  {role === "register"
                    ? "Approved register"
                    : role === "ledger"
                      ? "Ledger setup"
                      : "Retained bank evidence"}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fields.map((field) => (
              <tr key={field}>
                <th scope="row">
                  {field === "assertion_status"
                    ? "Declared account status"
                    : field.replaceAll("_", " ")}
                </th>
                {roles.map((role) => (
                  <td key={role} style={{ overflowWrap: "anywhere" }}>
                    {text(
                      rows.find((row) => row.source_role === role)?.[field],
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
