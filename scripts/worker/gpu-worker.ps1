# Thin standalone launcher; does not change ExecutionPolicy or system settings.
$ErrorActionPreference = 'Stop'
$workerScript = Join-Path $PSScriptRoot 'worker.py'
foreach ($candidate in @('python', 'py')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $prefix = @()
        if ($candidate -eq 'py') { $prefix = @('-3') }
        & $candidate @prefix -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>$null
        if ($LASTEXITCODE -eq 0) {
            & $candidate @prefix $workerScript @args
            exit $LASTEXITCODE
        }
    }
}
Write-Error 'Python 3.10+ is required on the GPU host.'
exit 1
