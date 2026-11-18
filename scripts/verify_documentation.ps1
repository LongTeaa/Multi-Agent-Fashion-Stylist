$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$requiredFiles = @(
    'AGENTS.md',
    'CURRENT_STATE.md',
    'thesis/tro_ly_phoi_do_thong_minh_multi_agent.md',
    'docs/README.md',
    'docs/01_product/PRD_MVP.md',
    'docs/02_architecture/SYSTEM_ARCHITECTURE.md',
    'docs/02_architecture/MULTI_AGENT_SPEC.md',
    'docs/03_domain/FASHION_KNOWLEDGE_BASE.md',
    'docs/03_domain/INGESTION_AND_RETRIEVAL_SPEC.md',
    'docs/04_data/DATA_SCHEMA.md',
    'docs/04_data/OBJECT_STORAGE_SPEC.md',
    'docs/05_api/API_CONTRACT.md',
    'docs/06_features/PERSONALIZATION_AND_FEEDBACK_SPEC.md',
    'docs/06_features/VIRTUAL_TRYON_SPEC.md',
    'docs/07_implementation/ROADMAP.md',
    'docs/07_implementation/ALIGNMENT_BACKLOG.md',
    'docs/07_implementation/TEST_STRATEGY.md',
    'docs/07_implementation/VIBE_CODING_GUIDE.md',
    'docs/archive/README.md',
    'docs/archive/MVP_ROADMAP.md'
)

$failures = [System.Collections.Generic.List[string]]::new()

foreach ($relativePath in $requiredFiles) {
    $absolutePath = Join-Path $workspaceRoot $relativePath
    if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
        $failures.Add("Missing required file: $relativePath")
    }
}

$legacyThesisPath = Join-Path $workspaceRoot 'tro_ly_phoi_do_thong_minh_multi_agent.md'
if (Test-Path -LiteralPath $legacyThesisPath) {
    $failures.Add('The thesis file MUST exist only under thesis/.')
}

$normativeDirectories = Get-ChildItem -LiteralPath (Join-Path $workspaceRoot 'docs') -Directory |
    Where-Object { $_.Name -match '^0[1-7]_' }
foreach ($directory in $normativeDirectories) {
    $reports = Get-ChildItem -LiteralPath $directory.FullName -Recurse -File |
        Where-Object { $_.Name -match '_\d{4}-\d{2}-\d{2}\.(md|json)$' -or $_.Name -match '(SPIKE|AUDIT)_REPORT' }
    foreach ($report in $reports) {
        $failures.Add("Dated or evidence report MUST live under docs/archive/reports/: $($report.FullName.Substring($workspaceRoot.Length + 1))")
    }
}
if (Test-Path -LiteralPath (Join-Path $workspaceRoot 'ADVERSARIAL_AUDIT_REPORT.md')) {
    $failures.Add('ADVERSARIAL_AUDIT_REPORT.md MUST live under docs/archive/reports/.')
}

$governanceFiles = @(
    (Join-Path $workspaceRoot 'AGENTS.md'),
    (Join-Path $workspaceRoot 'CURRENT_STATE.md')
)
$documentationFiles = Get-ChildItem -LiteralPath (Join-Path $workspaceRoot 'docs') -Recurse -Filter '*.md' -File
$auditedFiles = @($governanceFiles) + @($documentationFiles.FullName)

foreach ($filePath in $auditedFiles) {
    if (-not (Test-Path -LiteralPath $filePath)) {
        continue
    }

    $content = Get-Content -Raw -Encoding UTF8 -LiteralPath $filePath
    $relativeFile = $filePath.Substring($workspaceRoot.Length + 1)

    $fenceCount = ([regex]::Matches($content, '(?m)^```')).Count
    if ($fenceCount % 2 -ne 0) {
        $failures.Add("Unbalanced Markdown code fences: $relativeFile")
    }

    $isArchived = $relativeFile -match '^docs[\\/]archive[\\/]'
    if ($filePath -like (Join-Path $workspaceRoot 'docs\*') -and
        -not $isArchived -and
        $content -notmatch '\bMUST\b|\bSHOULD\b|\bINVARIANT\b') {
        $failures.Add("Missing RFC keyword usage: $relativeFile")
    }

    $legacyPatterns = @(
        '../tro_ly_phoi_do_thong_minh_multi_agent.md',
        'docs/01_PRD_MVP.md',
        'docs/02_SYSTEM_ARCHITECTURE.md',
        'docs/03_MULTI_AGENT_SPEC.md',
        'docs/04_FASHION_KNOWLEDGE_BASE.md',
        'docs/05_DATA_SCHEMA.md',
        'docs/06_API_CONTRACT.md',
        'docs/07_VIRTUAL_TRYON_SPEC.md',
        'docs/08_MVP_ROADMAP_CHECKLIST.md',
        'docs/07_implementation/MVP_ROADMAP.md'
    )
    foreach ($legacyPattern in $legacyPatterns) {
        if ($content.Contains($legacyPattern)) {
            $failures.Add("Legacy documentation reference '$legacyPattern' in $relativeFile")
        }
    }

    foreach ($match in [regex]::Matches($content, '(?:docs/|thesis/|\.\./)[A-Za-z0-9_./-]+\.md')) {
        $reference = $match.Value
        if ($reference.StartsWith('docs/') -or $reference.StartsWith('thesis/')) {
            $target = Join-Path $workspaceRoot $reference
        }
        else {
            $target = Join-Path (Split-Path -Parent $filePath) $reference
        }
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
            $failures.Add("Broken Markdown reference '$reference' in $relativeFile")
        }
    }
}

$commandBlockPattern = '(?m)^\*\*Executable Commands?:\*\*\r?$'

$archivedRoadmap = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $workspaceRoot 'docs/archive/MVP_ROADMAP.md')
if (([regex]::Matches($archivedRoadmap, '(?m)^## Phase [1-7] ')).Count -ne 7) {
    $failures.Add('docs/archive/MVP_ROADMAP.md MUST keep exactly seven phases.')
}
if (([regex]::Matches($archivedRoadmap, $commandBlockPattern)).Count -ne 7) {
    $failures.Add('Every archived MVP roadmap phase MUST keep its executable command block.')
}

$roadmap = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $workspaceRoot 'docs/07_implementation/ROADMAP.md')
$roadmapPhaseCount = ([regex]::Matches($roadmap, '(?m)^## Phase \d+ ')).Count
if (([regex]::Matches($roadmap, $commandBlockPattern)).Count -ne $roadmapPhaseCount) {
    $failures.Add('Every ROADMAP.md phase MUST define exactly one executable command block.')
}

$testStrategy = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $workspaceRoot 'docs/07_implementation/TEST_STRATEGY.md')
foreach ($phase in 1..7) {
    if ($testStrategy -notmatch "(?m)^\| $phase \|") {
        $failures.Add("TEST_STRATEGY.md is missing the Phase $phase matrix row.")
    }
}
foreach ($providerSection in @('LLM and Context Extraction', 'Vision and Detection', 'Weather', 'Object Storage and Image Generation', 'Time and Randomness')) {
    if (-not $testStrategy.Contains($providerSection)) {
        $failures.Add("TEST_STRATEGY.md is missing mock strategy: $providerSection")
    }
}

$guide = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $workspaceRoot 'docs/07_implementation/VIBE_CODING_GUIDE.md')
foreach ($anchor in @('Context Anchor', 'Spec Files', 'Specific Task', 'Verification Command')) {
    if (-not $guide.Contains($anchor)) {
        $failures.Add("VIBE_CODING_GUIDE.md is missing prompt anchor: $anchor")
    }
}

$schema = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $workspaceRoot 'docs/04_data/DATA_SCHEMA.md')
foreach ($table in @('ingestion_batches', 'ingestion_detections', 'media_assets', 'wardrobe_items', 'outfit_recommendations', 'outfit_items', 'ratings', 'feedback_prompt_state', 'wear_logs', 'tryon_renders')) {
    if (-not $schema.Contains("``$table``")) {
        $failures.Add("DATA_SCHEMA.md is missing table: $table")
    }
}

$api = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $workspaceRoot 'docs/05_api/API_CONTRACT.md')
foreach ($endpoint in @('/ingestions', '/wardrobe/items', '/stylist/chat', '/user/profile', '/outfits/{outfit_id}/rating', '/outfits/{outfit_id}/worn', '/tryons', '/media/{media_asset_id}')) {
    if (-not $api.Contains($endpoint)) {
        $failures.Add("API_CONTRACT.md is missing endpoint: $endpoint")
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Output "Documentation verification passed ($($requiredFiles.Count) required files, $roadmapPhaseCount active roadmap phases)."
