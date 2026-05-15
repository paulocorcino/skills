param(
    [string]$Item,
    [switch]$Next,
    [switch]$OpenNext,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $root = git rev-parse --show-toplevel 2>$null
    if (-not $root) {
        throw "This script must run inside a git repository."
    }
    return (Resolve-Path $root).Path
}

function Get-BacklogFiles($RepoRoot) {
    Get-ChildItem -Path (Join-Path $RepoRoot "docs/backlog") -Filter "*.md" |
        Where-Object { $_.Name -match "^\d{3}-" } |
        Sort-Object Name
}

function Test-BacklogDelivered($Path) {
    $content = Get-Content -Raw -Path $Path
    $labelsDelivered = $content -match "(?m)^Labels:.*`?delivered`?"
    $statusDelivered = $content -match "(?m)^Status:\s+delivered\b"
    return ($labelsDelivered -or $statusDelivered)
}

function Resolve-BacklogItem($RepoRoot, $Item, [bool]$UseNext) {
    $files = Get-BacklogFiles $RepoRoot
    if ($UseNext) {
        $nextFile = $files | Where-Object { -not (Test-BacklogDelivered $_.FullName) } | Select-Object -First 1
        if (-not $nextFile) {
            throw "No undelivered backlog item found under docs/backlog."
        }
        return $nextFile.FullName
    }

    if (-not $Item) {
        throw "Provide -Item <NNN|path> or use -Next."
    }

    if (Test-Path $Item) {
        return (Resolve-Path $Item).Path
    }

    $normalized = $Item.Trim()
    if ($normalized -match "^\d{1,3}$") {
        $normalized = $normalized.PadLeft(3, "0")
        $match = $files | Where-Object { $_.Name.StartsWith("$normalized-") } | Select-Object -First 1
        if ($match) {
            return $match.FullName
        }
    }

    $nameMatch = $files | Where-Object { $_.Name -like "*$normalized*" } | Select-Object -First 1
    if ($nameMatch) {
        return $nameMatch.FullName
    }

    throw "Could not resolve backlog item '$Item'."
}

function Get-NextAfter($RepoRoot, $CurrentPath) {
    $files = @(Get-BacklogFiles $RepoRoot)
    $currentName = Split-Path -Leaf $CurrentPath
    $afterCurrent = $false
    foreach ($file in $files) {
        if ($afterCurrent -and -not (Test-BacklogDelivered $file.FullName)) {
            return $file.FullName
        }
        if ($file.Name -eq $currentName) {
            $afterCurrent = $true
        }
    }
    return $null
}

$repoRoot = Get-RepoRoot
$backlogPath = Resolve-BacklogItem $repoRoot $Item ([bool]$Next)
$relativeBacklogPath = Resolve-Path -Relative $backlogPath
$backlogContent = Get-Content -Raw -Path $backlogPath
$statusBefore = git -C $repoRoot status --short

$prompt = @"
Task: executar o backlog $relativeBacklogPath.

You are running from Codex CLI as the implementation executor for this repository.

Required execution model:
1. Read AGENTS.md/repository instructions and the backlog item below.
2. Produce a concise plan first.
3. Implement the backlog item end to end, staying within the requested backlog scope.
4. Inspect relevant files before editing.
5. Keep repository documentation and code comments in English.
6. Preserve the distinction between legacy runningprocess and AppUsage.
7. Treat process, user, browser, URL, window title, command line, and document data as sensitive.
8. Do not revert unrelated working-tree changes. Work with existing changes only when they belong to this backlog item.
9. Run the narrowest relevant validations.
10. Mark the backlog item delivered and update docs/backlog/README.md only after delivery evidence exists.
11. Final response must list files changed, important decisions, validations run, and validations skipped or unavailable.

Initial git status:
``````
$statusBefore
``````

Backlog item path: $relativeBacklogPath

Backlog item contents:
``````
$backlogContent
``````
"@

if ($DryRun) {
    $prompt
    exit 0
}

$promptFile = Join-Path ([System.IO.Path]::GetTempPath()) ("backlog-codex-{0}.txt" -f ([System.Guid]::NewGuid().ToString("N")))
Set-Content -Path $promptFile -Value $prompt -Encoding UTF8

try {
    Get-Content -Raw -Path $promptFile | codex exec -C $repoRoot -m gpt-5.5 -c 'model_reasoning_effort="medium"' -s danger-full-access -a never -
    $exitCode = $LASTEXITCODE
}
finally {
    Remove-Item -Path $promptFile -Force -ErrorAction SilentlyContinue
}

$nextPath = Get-NextAfter $repoRoot $backlogPath
Write-Host ""
Write-Host "Backlog item executed: $relativeBacklogPath"
if ($nextPath) {
    $nextRelative = Resolve-Path -Relative $nextPath
    Write-Host "Next backlog item: $nextRelative"
    if ($OpenNext) {
        code -r $nextPath
    }
}
else {
    Write-Host "No later undelivered backlog item found."
}

exit $exitCode
