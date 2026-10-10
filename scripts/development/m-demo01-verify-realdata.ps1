# DEMO-ONLY (M-DEMO01): verify the committed receipt against local CVAT and LabelX APIs.
[CmdletBinding()]
param(
    [string]$LabelXBaseUrl = "http://127.0.0.1:8000",
    [string]$CvatBaseUrl = "http://localhost:8080",
    [string]$Username = $env:LABELX_DEMO_USERNAME,
    [string]$Password = $env:LABELX_DEMO_PASSWORD,
    [string]$CvatToken = $env:CVAT_SERVICE_TOKEN,
    [string]$ReceiptPath = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($ReceiptPath)) {
    $ReceiptPath = Join-Path $root "fixtures\demo\m-demo01-bdd100k-realdata-receipt.json"
}
if ([string]::IsNullOrWhiteSpace($Username) -or [string]::IsNullOrWhiteSpace($Password)) {
    throw "Set LABELX_DEMO_USERNAME and LABELX_DEMO_PASSWORD."
}
if ([string]::IsNullOrWhiteSpace($CvatToken)) {
    throw "Set CVAT_SERVICE_TOKEN to a read-only CVAT token."
}

function Assert-Equal {
    param([string]$Name, $Actual, $Expected)
    if ((ConvertTo-Json $Actual -Compress) -ne (ConvertTo-Json $Expected -Compress)) {
        throw "$Name mismatch: actual=$Actual expected=$Expected"
    }
}

$receipt = Get-Content $ReceiptPath -Raw | ConvertFrom-Json
$labelx = $LabelXBaseUrl.TrimEnd("/")
$cvat = $CvatBaseUrl.TrimEnd("/")
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-WebRequest -Uri "$labelx/api/auth/csrf/" -WebSession $session -UseBasicParsing | Out-Null
$csrf = ($session.Cookies.GetCookies($labelx) | Where-Object Name -eq "csrftoken").Value
$loginBody = @{ username = $Username; password = $Password } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$labelx/api/auth/login/" -WebSession $session `
    -Headers @{ "X-CSRFToken" = $csrf } -ContentType "application/json" `
    -Body $loginBody | Out-Null

$snapshot = Invoke-RestMethod -Method Get `
    -Uri "$labelx/api/snapshots/$($receipt.snapshot.snapshot_id)/" -WebSession $session
$frames = Invoke-RestMethod -Method Get `
    -Uri "$labelx/api/runs/$($receipt.run.run_id)/frames/?page_size=100" -WebSession $session
$image = Invoke-WebRequest -Uri ($labelx + $frames.items[0].image_url) `
    -WebSession $session -UseBasicParsing

$cvatHeaders = @{ Authorization = "Bearer $CvatToken" }
$task = Invoke-RestMethod -Method Get `
    -Uri "$cvat/api/tasks/$($receipt.source.cvat_task_id)" -Headers $cvatHeaders
$annotations = Invoke-RestMethod -Method Get `
    -Uri "$cvat/api/jobs/$($receipt.source.cvat_job_id)/annotations" -Headers $cvatHeaders
$annotationCount = @($annotations.shapes).Count + @($annotations.tags).Count
foreach ($track in @($annotations.tracks)) {
    $annotationCount += @($track.shapes).Count
}
$frameCount = ($snapshot.jobs | ForEach-Object { $_.frames.Count } | Measure-Object -Sum).Sum
$engineStates = @($frames.engines | ForEach-Object { $_.engine + ":" + $_.status })
$expectedEngineStates = @($receipt.api.engines | ForEach-Object { $_.engine + ":" + $_.status })

Assert-Equal "snapshot.status" $snapshot.status $receipt.snapshot.status
Assert-Equal "snapshot.revision" $snapshot.revision_hash $receipt.snapshot.revision_sha256
Assert-Equal "snapshot.jobs" $snapshot.jobs.Count $receipt.snapshot.job_count
Assert-Equal "snapshot.frames" $frameCount $receipt.snapshot.frame_count
Assert-Equal "cvat.task.size" $task.size $receipt.source.frame_count
Assert-Equal "cvat.annotations" $annotationCount $receipt.source.annotation_count
Assert-Equal "api.items" $frames.items.Count $receipt.api.item_count
Assert-Equal "api.ranks" @($frames.items | ForEach-Object rank) @($receipt.api.ranks)
Assert-Equal "api.scores" @($frames.items | ForEach-Object score) @($receipt.api.scores)
Assert-Equal "api.engines" $engineStates $expectedEngineStates
Assert-Equal "api.image.status" $image.StatusCode $receipt.api.top_frame.image_status
Assert-Equal "api.image.bytes" $image.RawContentStream.Length $receipt.api.top_frame.image_bytes
Assert-Equal "api.cvat.deep_link" $frames.items[0].cvat.deep_link `
    $receipt.api.top_frame.cvat_deep_link

[PSCustomObject]@{
    result = "passed"
    snapshot_id = $snapshot.id
    run_id = $frames.run_id
    frames = $frames.items.Count
    annotations = $annotationCount
    engines = $engineStates
    top_frame_image_bytes = $image.RawContentStream.Length
} | ConvertTo-Json
