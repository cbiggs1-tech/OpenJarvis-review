# minimize_power.ps1 — Disable unnecessary services/startup items on Beelink
# KEEPS: VS Code, Slack, Chrome, OpenJarvis
# Run from elevated PowerShell (Run as Administrator)

Write-Host "=== Beelink Power Minimization ===" -ForegroundColor Cyan

# --- Disable unnecessary services ---
$services = @(
    'SysMain',          # Superfetch — high disk/RAM usage, not needed
    'DiagTrack',        # Windows telemetry
    'WerSvc',           # Windows Error Reporting
    'WMPNetworkSvc',    # Windows Media Player network sharing
    'Fax',              # Fax service
    'XblAuthManager',   # Xbox Live auth
    'XblGameSave',      # Xbox Live game save
    'XboxNetApiSvc',    # Xbox networking
    'XboxGipSvc',       # Xbox accessories
    'RemoteRegistry',   # Remote registry access
    'MapsBroker',       # Downloaded maps manager
    'lfsvc',            # Geolocation
    'wisvc',            # Windows Insider service
    'RetailDemo',       # Retail demo mode
    'wlidsvc',          # Microsoft Account sign-in — optional, disable if not using MS account features
    'TabletInputService', # Tablet PC input — not needed on mini PC
    'TrkWks',           # Distributed Link Tracking — not needed
    'WbioSrvc',         # Windows Biometric (fingerprint) — not needed
    'PhoneSvc',         # Phone service
    'lltdsvc',          # Link-Layer Topology Discovery
    'SCardSvr',         # Smart Card — not needed
    'SCPolicySvc',      # Smart Card removal policy
    'UevAgentService',  # User Experience Virtualization
    'WpcMonSvc',        # Parental controls
    'WPDBusEnum',       # Portable Device Enumerator (cameras/phones)
    'icssvc',           # Windows Mobile Hotspot
    'NcdAutoSetup',     # Network Connected Device auto-setup
    'CDPUserSvc',       # Connected Devices Platform (per-user) — can cause high CPU
    'OneSyncSvc',       # Sync host (MS account sync)
    'MessagingService', # SMS/MMS
    'PimIndexMaintenanceSvc', # Contacts index
    'UserDataSvc'       # User data access
)

foreach ($svc in $services) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s) {
        try {
            Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
            Set-Service -Name $svc -StartupType Disabled -ErrorAction SilentlyContinue
            Write-Host "  Disabled: $svc" -ForegroundColor Green
        } catch {
            Write-Host "  Skipped (locked): $svc" -ForegroundColor Yellow
        }
    }
}

# --- Pause Windows Update (prevents surprise CPU/disk spikes) ---
Write-Host "`nPausing Windows Update..." -ForegroundColor Cyan
$wuPath = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
if (-not (Test-Path $wuPath)) { New-Item -Path $wuPath -Force | Out-Null }
Set-ItemProperty -Path $wuPath -Name "NoAutoUpdate" -Value 1 -Type DWord -Force
Set-ItemProperty -Path $wuPath -Name "AUOptions" -Value 1 -Type DWord -Force

# Also use the WU pause API
$wuPausePath = "HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
if (Test-Path $wuPausePath) {
    Set-ItemProperty -Path $wuPausePath -Name "PauseUpdatesExpiryTime" -Value "2026-06-01T00:00:00Z" -Type String -Force -ErrorAction SilentlyContinue
    Set-ItemProperty -Path $wuPausePath -Name "PauseFeatureUpdatesStartTime" -Value "2026-03-01T00:00:00Z" -Type String -Force -ErrorAction SilentlyContinue
    Set-ItemProperty -Path $wuPausePath -Name "PauseQualityUpdatesStartTime" -Value "2026-03-01T00:00:00Z" -Type String -Force -ErrorAction SilentlyContinue
}
Write-Host "  Windows Update paused" -ForegroundColor Green

# --- Disable startup items (registry) ---
# Keep: slack, chrome, code (VS Code), jarvis
Write-Host "`nCleaning startup registry entries..." -ForegroundColor Cyan
$startupKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$keep = @('slack', 'chrome', 'code', 'jarvis', 'securityhealth', 'windowsdefender')
$entries = Get-ItemProperty -Path $startupKey -ErrorAction SilentlyContinue
if ($entries) {
    $entries.PSObject.Properties | Where-Object {
        $_.Name -notmatch '^PS' -and
        ($keep | Where-Object { $_.Name.ToLower() -like "*$_*" }).Count -eq 0
    } | ForEach-Object {
        try {
            Remove-ItemProperty -Path $startupKey -Name $_.Name -ErrorAction SilentlyContinue
            Write-Host "  Removed startup: $($_.Name)" -ForegroundColor Green
        } catch {}
    }
}

# Machine-level startup
$startupKeyLM = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
$entriesLM = Get-ItemProperty -Path $startupKeyLM -ErrorAction SilentlyContinue
if ($entriesLM) {
    $entriesLM.PSObject.Properties | Where-Object {
        $_.Name -notmatch '^PS' -and
        ($keep | Where-Object { $_.Name.ToLower() -like "*$_*" }).Count -eq 0 -and
        $_.Name -notmatch 'SecurityHealth|WindowsDefender|MsMpEng'
    } | ForEach-Object {
        try {
            Remove-ItemProperty -Path $startupKeyLM -Name $_.Name -ErrorAction SilentlyContinue
            Write-Host "  Removed HKLM startup: $($_.Name)" -ForegroundColor Green
        } catch {}
    }
}

# --- Set power plan to Balanced with conservative CPU limits ---
Write-Host "`nApplying conservative power settings..." -ForegroundColor Cyan
# Balanced plan GUID
$balanced = "381b4222-f694-41f0-9685-ff5bb260df2e"
powercfg /setactive $balanced 2>$null

# CPU min 0%, max 70% — lower than before to reduce heat/power
powercfg /setacvalueindex $balanced SUB_PROCESSOR PROCTHROTTLEMIN 0
powercfg /setacvalueindex $balanced SUB_PROCESSOR PROCTHROTTLEMAX 70
# Turn off display after 5 min (saves power when idle)
powercfg /setacvalueindex $balanced SUB_VIDEO VIDEOIDLE 300
# Sleep: never (so Jarvis keeps running)
powercfg /setacvalueindex $balanced SUB_SLEEP STANDBYIDLE 0
powercfg /setactive $balanced
Write-Host "  CPU max 70%, display off after 5min, sleep never" -ForegroundColor Green

# --- Disable scheduled tasks that waste CPU ---
Write-Host "`nDisabling noisy scheduled tasks..." -ForegroundColor Cyan
$noisyTasks = @(
    '\Microsoft\Windows\Customer Experience Improvement Program\Consolidator',
    '\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip',
    '\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser',
    '\Microsoft\Windows\Application Experience\ProgramDataUpdater',
    '\Microsoft\Windows\Autochk\Proxy',
    '\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector',
    '\Microsoft\Windows\Feedback\Siuf\DmClient',
    '\Microsoft\Windows\Maps\MapsUpdateTask',
    '\Microsoft\Windows\Maps\MapsToastTask',
    '\Microsoft\Windows\Windows Error Reporting\QueueReporting'
)
foreach ($task in $noisyTasks) {
    Disable-ScheduledTask -TaskPath (Split-Path $task) -TaskName (Split-Path $task -Leaf) -ErrorAction SilentlyContinue | Out-Null
    Write-Host "  Disabled task: $(Split-Path $task -Leaf)" -ForegroundColor Green
}

Write-Host "`n=== Done. Reboot recommended. ===" -ForegroundColor Cyan
Write-Host "Keeping active: VS Code, Slack, Chrome, OpenJarvis" -ForegroundColor White
