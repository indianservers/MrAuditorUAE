"""Render verified local experiment receipts; never generates model-quality numbers."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/ml-foundation"
report = json.loads((DOCS / "benchmark.json").read_text())
details = {
    "journal-anomaly": ["Legacy line autoencoder", "Normal/relevant-exception review labels unproven on client records", "Journal context, train-only robust features, validation threshold, baseline queue comparison", "Real normal-population assumptions, contamination and entity/period stability remain unverified"],
    "journal-type": ["Legacy binary exception classifier", "Ten reviewed journal-type labels must be collected", "True multiclass taxonomy, class weighting, abstention, train-fitted centroid baseline", "Neural model underperformed baseline at tested settings; real-client evaluation required"],
    "account-mapping": ["Legacy five-class hashed English name features", "Canonical account-mapping labels must be reviewed", "Unicode names/descriptions plus ledger behavior; canonical taxonomy; ambiguity review", "No legal/tax treatment inferred; real-client evaluation required"],
    "review-ranking": ["Legacy binary review classifier and explicit baselines", "Sufficient reviewed outcomes not established", "Configurable earlier-period rules/statistics baseline and label-gated supervised experiments", "No client risk model or measured queue usefulness without outcomes"],
}
matrix = []
for experiment in report["experiments"]:
    task = experiment["task"]
    prior, data, fixes, gap = details[task]
    matrix.append({"capability": task, "existing": prior, "actual_runtime": "Synthetic CPU train/reload/infer verified; no client deployment asserted",
                   "training_data": data, "model_availability": "Local synthetic experimental artifact; private governed production registry unchanged",
                   "quality_evidence": experiment["evaluation"], "selection": experiment["selection"], "fixes": fixes, "remaining_gap": gap})
(DOCS / "audit-matrix.json").write_text(json.dumps({"source": "Repository inspection plus actual local CPU experiments", "measured_at": report["measured_at"],
    "native_probe": {"node": "v24.15.0", "tfjs_node": "4.22.0", "platform": "Windows x64", "status": "failed", "reasons": ["Windows CPU prebuilt binary HTTP 404", "Source-build fallback reported missing Windows SDK"], "selected_backend": "verified JavaScript CPU"},
    "capabilities": matrix}, indent=2))
headers = ["Capability", "Existing", "Actual runtime", "Training data", "Model availability", "Fixes", "Remaining gap"]
rows = [[r[k] for k in ["capability", "existing", "actual_runtime", "training_data", "model_availability", "fixes", "remaining_gap"]] for r in matrix]
metrics = [[e["task"], round(e["training"]["duration_ms"], 3), round(e["cold_model_load_and_batch_ms"], 3), round(e["warm_batch_ms"]["mean"], 3), e["tensors_after_disposal"], e["selection"]["preferred_execution_mode"]] for e in report["experiments"]]
def table(headings, body):
    return '<table><thead><tr>' + ''.join('<th>' + html.escape(str(v)) + '</th>' for v in headings) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + html.escape(str(v)) + '</td>' for v in row) + '</tr>' for row in body) + '</tbody></table>'
(DOCS / "audit-matrix.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>TheAuditor ML foundation audit</title><style>body{font:15px system-ui;margin:32px;color:#17212b}h1{font-size:24px}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{text-align:left;vertical-align:top;border:1px solid #d4dae0;padding:10px}th{background:#edf1f4}small{color:#425466}</style><h1>TheAuditor local ML foundation</h1><p>CPU mechanics verified. Real-client quality and production readiness remain unproven. Use cases 51–100 were not implemented.</p><small>Measured ' + html.escape(report['measured_at']) + ' · Synthetic fixtures only</small>' + table(headers, rows) + '<h2>Measured local performance</h2>' + table(["Task", "Training ms", "Cold model + batch ms", "Warm batch mean ms", "Tensors after disposal", "Validation preference"], metrics) + '<p>20 warm iterations; small synthetic batches; shared-machine timings. Native CPU probe failed; JavaScript CPU verified. No external language model was required.</p><p><a href="README.md">Implementation, APIs and limitations</a> · <a href="benchmark.json">Complete benchmark evidence</a></p></html>', encoding='utf-8')
canvas = '''import {H1,H2,Text,Table,Stack} from 'cursor/canvas';
const auditRows=__AUDIT__;
const metricRows=__METRICS__;
export default function MLFoundationAudit(){return <Stack style={{padding:24,gap:16}}>
<H1>TheAuditor local ML foundation</H1>
<Text>CPU training, reload and inference mechanics verified. Real-client quality and production readiness remain unproven. Use cases 51–100 were not implemented.</Text>
<Text tone="secondary" size="small">Source: actual local CPU synthetic experiments · __DATE__ · Windows x64 / Node 24.15.0 / TensorFlow.js 4.22.0</Text>
<H2>Capability audit</H2><Table headers={__HEADERS__} rows={auditRows} stickyHeader />
<H2>Measured local performance</H2><Text>20 warm iterations per task. Small synthetic workloads, including integrity checks. These are observations, not performance targets.</Text>
<Table headers={['Task','Training (ms)','Cold model + batch (ms)','Warm batch mean (ms)','Tensors after disposal','Validation preference']} rows={metricRows} />
<H2>Decisions and limits</H2><Text>Native CPU installation failed: prebuilt binary 404 and missing Windows SDK during source fallback. Verified JavaScript CPU remains operational. Neural journal/account classifiers underperformed simpler centroid baselines at tested settings. No automatic model promotion occurred.</Text>
<Text>Private artifacts, approved evidence, tenant/engagement permissions and source freshness are retained. New APIs support reviewed labels, queued training, explicit centroid scoring and configurable earlier-period review baselines. Cross-entity generalization and real-client accuracy have not been established.</Text>
</Stack>}
'''.replace('__AUDIT__', json.dumps(rows)).replace('__METRICS__', json.dumps(metrics)).replace('__DATE__', report['measured_at']).replace('__HEADERS__', json.dumps(headers))
target = Path.home() / '.cursor/projects/c-Indian-Servers-TheAuditor/canvases/ml-foundation-audit.canvas.tsx'
target.write_text(canvas, encoding='utf-8')
print(json.dumps({"capabilities": len(matrix), "canvas": str(target), "report": str(DOCS / 'audit-matrix.html')}))
