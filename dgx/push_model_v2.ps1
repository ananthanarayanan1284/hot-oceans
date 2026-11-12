# Upload the improved model (honest task, threshold-relative features) to the DGX and run Stage E (model), the trust
# checks and Stage F (Lakshadweep case study) on the full basin. The dashboard export is left for later.
# Run from the project folder when the DGX is reachable (university network):
#   powershell -ExecutionPolicy Bypass -File dgx\push_model_v2.ps1
$ErrorActionPreference = "Stop"
$py = "C:\Users\anant\miniforge3\envs\hot-oceans\python.exe"
$files = @("config.yaml", "pipeline/features.py", "pipeline/stage_e_model.py", "pipeline/stage_e_trust.py",
           "pipeline/stage_f_case_study.py", "pipeline/export_dashboard.py", "tests/test_hobday.py", "dashboard/app.py")
foreach ($f in $files) { & $py -W ignore dgx\jhub.py upload ($f -replace "/", "\") "hot-oceans/$f" }
# tests, then remove the old (hindsight-based) feature tables to free space on the shared disk, then run
& $py -W ignore dgx\jhub.py run ("cd ~/hot-oceans && source ~/miniforge3/etc/profile.d/conda.sh && conda activate hot-oceans " +
    "&& python -m pytest tests -q -p no:cacheprovider 2>&1 | tail -1 " +
    "&& rm -rf data/full/lake/training data/full/lake/neighbours") --timeout 300
# Launch on its own line: only the detached run goes to the background (a backgrounded && chain dies with the terminal).
& $py -W ignore dgx\jhub.py run ("cd ~/hot-oceans; setsid nohup bash dgx/run_full.sh stage_e_model stage_e_trust " +
    "stage_f_case_study > logs/model_v2.log 2>&1 < /dev/null & sleep 30; cat ~/hot-oceans/logs/model_v2.log") --timeout 120
"Started. Check progress with:"
'  python -W ignore dgx\jhub.py run "tail -5 ~/hot-oceans/logs/model_v2.log; tail -3 ~/hot-oceans/logs/stage_e_model_full.log"'
