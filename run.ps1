param([string]$Python = "py", [switch]$Offline)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Install Python 3.12 and rerun." }
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
$taskPipelineArgs = @("pipeline.py")
if ($Offline) { $taskPipelineArgs += "--offline" }
& .\.venv\Scripts\python.exe @taskPipelineArgs
if ($LASTEXITCODE -ne 0) { throw "NASA pipeline failed." }
foreach ($taskScript in @("window_experiment.py", "build_dashboard.py", "phase2.py", "phase3.py")) {
    & .\.venv\Scripts\python.exe $taskScript
    if ($LASTEXITCODE -ne 0) { throw "Experiment failed: $taskScript" }
}
& .\.venv\Scripts\python.exe -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
Write-Output "NASA experiments complete. CALCE inspection and final model freeze are optional, separate steps; see README."
