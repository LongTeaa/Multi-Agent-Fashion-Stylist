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
    'docs/07_implementation/MVP_ROADMAP.md',
    'docs/07_implementation/TEST_STRATEGY.md',
    'docs/07_implementation/VIBE_CODING_GUIDE.md'
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

    $isLiveTestReport = $relativeFile -match '(^|[\\/])LIVE_TEST_ISSUES_[^\\/]+\.md$'
    if ($filePath -like (Join-Path $workspaceRoot 'docs\*') -and
        -not $isLiveTestReport -and
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
        'docs/08_MVP_ROADMAP_CHECKLIST.md'
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

$roadmap = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $workspaceRoot 'docs/07_implementation/MVP_ROADMAP.md')
if (([regex]::Matches($roadmap, '(?m)^## Phase [1-7] ')).Count -ne 7) {
    $failures.Add('MVP_ROADMAP.md MUST define exactly seven phases.')
}
if (([regex]::Matches($roadmap, '(?m)^\*\*Executable Commands?:\*\*\r?$')).Count -ne 7) {
    $failures.Add('Every roadmap phase MUST define an executable command block.')
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

Write-Output "Documentation verification passed ($($requiredFiles.Count) required files, 7 roadmap phases)."
