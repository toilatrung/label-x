# DEMO-ONLY (M-DEMO01 / D-01): create or replay the locked BDD100K demo snapshot via API.
[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$DatasetId = 3,
    [int]$TaskId = 21,
    [string]$Username = $env:LABELX_DEMO_USERNAME,
    [string]$Password = $env:LABELX_DEMO_PASSWORD,
    [string]$IdempotencyKey = "m-demo01-d01-bdd100k-task21-v1"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Username) -or [string]::IsNullOrWhiteSpace($Password)) {
    throw "Set LABELX_DEMO_USERNAME and LABELX_DEMO_PASSWORD before running this script."
}

$base = $BaseUrl.TrimEnd("/")
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-WebRequest -Uri "$base/api/auth/csrf/" -WebSession $session -UseBasicParsing | Out-Null
$csrf = ($session.Cookies.GetCookies($base) | Where-Object Name -eq "csrftoken").Value

$loginBody = @{ username = $Username; password = $Password } | ConvertTo-Json
Invoke-RestMethod `
    -Method Post `
    -Uri "$base/api/auth/login/" `
    -WebSession $session `
    -Headers @{ "X-CSRFToken" = $csrf } `
    -ContentType "application/json" `
    -Body $loginBody | Out-Null

$csrf = ($session.Cookies.GetCookies($base) | Where-Object Name -eq "csrftoken").Value
$snapshotBody = @{
    dataset_id = $DatasetId
    scope = @{ cvat_task_ids = @($TaskId); cvat_job_ids = @() }
    note = "M-DEMO01 D-01 BDD100K val sample: task 21, job 18, 5 frames"
} | ConvertTo-Json -Depth 5

$accepted = Invoke-RestMethod `
    -Method Post `
    -Uri "$base/api/snapshots/" `
    -WebSession $session `
    -Headers @{ "X-CSRFToken" = $csrf; "Idempotency-Key" = $IdempotencyKey } `
    -ContentType "application/json" `
    -Body $snapshotBody
$snapshot = Invoke-RestMethod `
    -Method Get `
    -Uri "$base/api/snapshots/$($accepted.id)/" `
    -WebSession $session

$frameCount = ($snapshot.jobs | ForEach-Object { $_.frames.Count } | Measure-Object -Sum).Sum
[PSCustomObject]@{
    snapshot_id = $snapshot.id
    status = $snapshot.status
    revision_hash = $snapshot.revision_hash
    job_count = $snapshot.jobs.Count
    frame_count = $frameCount
    cvat_deep_link = $snapshot.jobs[0].cvat_url
    idempotency_key = $IdempotencyKey
} | ConvertTo-Json
