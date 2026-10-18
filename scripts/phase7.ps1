param([ValidateSet('backend','frontend','e2e','security','financial','ai','regression','benchmark','seed-demo','verify-demo','enrich-demo','demo-tax-cases','demo-scenarios','archive-demo')][string]$Task = 'regression')
$ErrorActionPreference = 'Stop'
$phase7Root = Split-Path -Parent $PSScriptRoot
function Invoke-Backend([string[]]$Arguments) {
    Push-Location (Join-Path $phase7Root 'backend')
    try {
        & '.venv/Scripts/python.exe' @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Backend command failed: $LASTEXITCODE" }
    } finally { Pop-Location }
}
function Invoke-Frontend([string[]]$Arguments) {
    Push-Location (Join-Path $phase7Root 'frontend')
    try {
        & npm.cmd @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Frontend command failed: $LASTEXITCODE" }
    } finally { Pop-Location }
}
switch ($Task) {
    'backend' { Invoke-Backend @('-m','pytest','--cov=app','--cov-report=term-missing') }
    'frontend' { Invoke-Frontend @('run','test'); Invoke-Frontend @('run','lint'); Invoke-Frontend @('run','typecheck'); Invoke-Frontend @('run','build') }
    'e2e' { Invoke-Frontend @('run','test:e2e:phase7') }
    'security' { Invoke-Backend @('-m','pytest','tests/integration','tests/phase7/test_worker_security.py','tests/phase7/test_vat_workflows.py') }
    'financial' { Invoke-Backend @('-m','pytest','tests/phase2/test_calculations.py','tests/phase5/test_calculations.py','tests/phase6/test_calculations.py','tests/phase7/test_vat_calculations.py') }
    'ai' { Invoke-Backend @('-m','pytest','tests/ai','tests/phase2/test_ai_storage.py','tests/phase4/test_ai_and_calculations.py','tests/phase6/test_grounding.py','tests/phase7/test_vat_workflows.py') }
    'regression' { & $PSCommandPath -Task backend; & $PSCommandPath -Task frontend; & $PSCommandPath -Task e2e }
    'benchmark' { Invoke-Backend @('../scripts/benchmark_accounting.py','--sizes','10000','100000','250000','--output','../docs/phase-7/scale-file-benchmarks.json') }
    'seed-demo' { Invoke-Backend @('../scripts/seed_demo.py') }
    'verify-demo' { Invoke-Backend @('../scripts/verify_demo.py') }
    'enrich-demo' { Invoke-Backend @('../scripts/enrich_demo.py') }
    'demo-tax-cases' { Invoke-Backend @('../scripts/demo_tax_cases.py') }
    'demo-scenarios' {
        Invoke-Backend @('../scripts/demo_accountant.py')
        Invoke-Backend @('../scripts/demo_audit.py')
        Invoke-Backend @('../scripts/demo_portal_invoice.py')
        Invoke-Backend @('../scripts/demo_role_calculations.py')
        Invoke-Backend @('../scripts/seed_demo.py')
        Invoke-Backend @('../scripts/verify_demo.py')
    }
    'archive-demo' {
        if (!$env:DEMO_ARCHIVE_CONFIRM) { throw 'Set DEMO_ARCHIVE_CONFIRM=ARCHIVE-{exact demo tenant UUID}. Archives only; immutable history remains.' }
        Invoke-Backend @('../scripts/seed_demo.py')
    }
}
