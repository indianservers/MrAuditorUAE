"use client";
function Value({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined)
    return <span>Not established</span>;
  if (depth > 8)
    return <span>Open the retained source for deeper supporting detail.</span>;
  if (Array.isArray(value))
    return (
      <>
        {value.slice(0, 50).map((item, i) => (
          <div key={i}>
            <Value value={item} depth={depth + 1} />
          </div>
        ))}
        {value.length > 50 && (
          <p>
            First 50 items shown; open the retained source for the complete
            population.
          </p>
        )}
      </>
    );
  if (typeof value === "object")
    return (
      <dl className="facts">
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <dt>{key.replaceAll("_", " ")}</dt>
            <dd>
              {item !== null && typeof item === "object" ? (
                <details open={key === "body" || key === "output"}>
                  <summary>Inspect {key.replaceAll("_", " ")}</summary>
                  <Value value={item} depth={depth + 1} />
                </details>
              ) : (
                <Value value={item} depth={depth + 1} />
              )}
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span>{String(value)}</span>;
}
export function BusinessEvidenceFacts({
  data,
}: {
  data: Record<string, unknown>;
}) {
  return <Value value={data} />;
}
