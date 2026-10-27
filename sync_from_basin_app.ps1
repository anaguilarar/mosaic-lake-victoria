# Refresh the release copy from the working copy before each GitHub upload (DEPLOYMENT_PLAN.md §5.2).
# Run from any directory:  powershell -ExecutionPolicy Bypass -File sync_from_basin_app.ps1
# robocopy exit codes 0-7 mean success. Only the data files the app serves from GitHub Pages are copied
# (site/js/config.js SITE); everything else is on Hugging Face, uploaded from basin_app\data.
$SRC = "D:\OneDrive - CGIAR\projects\MOSAIC\basin_app"
$DST = "D:\OneDrive - CGIAR\scripts\MOSAIC\victoria_basin_app"
New-Item -ItemType Directory -Force $DST | Out-Null

# app (mirror, so deleted files are removed too)
robocopy "$SRC\site" "$DST\site" /MIR /NFL /NDL /NJH /NP
if ($LASTEXITCODE -ge 8) { throw "robocopy site failed ($LASTEXITCODE)" }

# pipeline scripts only (no work\, no __pycache__); requirements.txt is kept in the release copy
robocopy "$SRC\prep" "$DST\prep" *.py README.md /XD work __pycache__ /NFL /NDL /NJH /NP
if ($LASTEXITCODE -ge 8) { throw "robocopy prep failed ($LASTEXITCODE)" }

# documentation the app links to
Copy-Item "$SRC\DATA_REPORT.md", "$SRC\STYLE.md" $DST -Force

# data served from GitHub Pages (keep in step with SITE in site/js/config.js and with .gitignore).
# Never copied: vectors\basin.geojson and basin_mask.geojson (ICPAC licence not specified).
foreach ($d in "meta", "series", "vectors", "figures", "fonts", "climate", "fire") {
    robocopy "$SRC\data\$d" "$DST\data\$d" /MIR /XF basin.geojson basin_mask.geojson /NFL /NDL /NJH /NP
    if ($LASTEXITCODE -ge 8) { throw "robocopy data\$d failed ($LASTEXITCODE)" }
}
robocopy "$SRC\data\query" "$DST\data\query" flood_query_100m.tif /NFL /NDL /NJH /NP
if ($LASTEXITCODE -ge 8) { throw "robocopy data\query failed ($LASTEXITCODE)" }
# terrain.pmtiles is 92.6 MB; GitHub refuses files over 100 MB - if a rebuild crosses that, drop it here
# and from SITE in config.js (the app then reads it from Hugging Face)
robocopy "$SRC\data\tiles" "$DST\data\tiles" s2_rgb.pmtiles osm_basemap.pmtiles terrain.pmtiles /NFL /NDL /NJH /NP
if ($LASTEXITCODE -ge 8) { throw "robocopy data\tiles failed ($LASTEXITCODE)" }

# safety checks: nothing internal, no withheld data, nothing GitHub refuses
$all = Get-ChildItem $DST -Recurse -File | Where-Object { $_.FullName -notmatch "\\\.git\\" }
$bad = $all | Where-Object {
    $_.Name -in @("ASSESSMENT.md", "AGENT_ACCESS.md", "DEPLOYMENT_PLAN.md", "basin.geojson", "basin_mask.geojson") -or
    $_.Name -like "DATA_REPORT.master_*" -or $_.FullName -match "\\(tests|\.taste-skill|work)\\" -or $_.Length -gt 100MB }
if ($bad) { $bad | ForEach-Object { Write-Warning "check: $($_.FullName)" } } else { "sync done: $DST" }
$big = $all | Where-Object { $_.Length -gt 25MB }
if ($big) { "over 25 MB (push with git, not the web upload):"; $big | ForEach-Object { "  {0,7:N1} MB  {1}" -f ($_.Length / 1MB), $_.FullName.Substring($DST.Length + 1) } }
"{0} files, {1:N1} MB" -f $all.Count, (($all | Measure-Object Length -Sum).Sum / 1MB)
