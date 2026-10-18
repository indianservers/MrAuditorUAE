"""Explicit synthetic CPU benchmarks; not a production capacity claim."""
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.modules.ifrs.calculations import calculate
from app.modules.ifrs.schemas import Mapping
from tests.phase5.test_calculations import ECL_INPUT

results=[]
for count in [1000,10000,20000]:
    body={**ECL_INPUT,"exposures":[{"reference":f"SYN-{i}","amount":"1000","stage":1} for i in range(count)]}
    start=time.perf_counter()
    output=calculate("ecl",body)
    elapsed=time.perf_counter()-start
    assert Decimal(output["total_ecl"])==count*65
    results.append({"engine":"ecl","rows":count,"scenarios":2,"seconds":round(elapsed,4),"independent_expected":str(count*65),"passed":True})
for count in [1000,10000]:
    body={"period_start":"2026-01-01","period_end":"2026-12-31","assets":[{"reference":f"SYN-{i}","cost":"3650","residual":"0","capitalisation_date":"2026-01-01","useful_life_years":"10","method":"straight_line"} for i in range(count)]}
    start=time.perf_counter();output=calculate("fixed-assets",body);elapsed=time.perf_counter()-start
    assert Decimal(output["total_depreciation"])==count*365
    results.append({"engine":"fixed-assets","rows":count,"seconds":round(elapsed,4),"independent_expected":str(count*365),"passed":True})
count=10000
body={"profile_id":"00000000-0000-0000-0000-000000000001","rationale":"Synthetic performance fixture","accounts":[{"account_code":str(i),"allocations":[{"line_code":"cash","label":"Cash","section":"assets","note":"N1"}]} for i in range(count)]}
start=time.perf_counter();Mapping.model_validate(body);elapsed=time.perf_counter()-start
results.append({"engine":"mapping-validation","rows":count,"seconds":round(elapsed,4),"passed":True})
target=Path(__file__).resolve().parents[1]/"docs/phase-5/benchmarks.json"
target.write_text(json.dumps({"scope":"Local Windows single process, validation + Decimal engine + serialization; excludes DB/network/export concurrency", "results":results},indent=2))
print(target.read_text())
