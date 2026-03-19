$python = "C:\openjarvis\.venv\Scripts\python.exe"
$runner = "C:\openjarvis\operator_runner.py"
$workdir = "C:\openjarvis"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

# news_digest — daily at 8am
$action = New-ScheduledTaskAction -Execute $python -Argument "$runner news_digest" -WorkingDirectory $workdir
$trigger = New-ScheduledTaskTrigger -Daily -At "08:00"
Register-ScheduledTask -TaskName "OpenJarvis-NewsDigest" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host "Registered: OpenJarvis-NewsDigest"

# researcher — every 30 minutes
$action = New-ScheduledTaskAction -Execute $python -Argument "$runner researcher" -WorkingDirectory $workdir
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 30) -Once -At (Get-Date).Date
Register-ScheduledTask -TaskName "OpenJarvis-Researcher" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host "Registered: OpenJarvis-Researcher"

# system_monitor — every 5 minutes
$action = New-ScheduledTaskAction -Execute $python -Argument "$runner system_monitor" -WorkingDirectory $workdir
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 5) -Once -At (Get-Date).Date
Register-ScheduledTask -TaskName "OpenJarvis-SystemMonitor" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host "Registered: OpenJarvis-SystemMonitor"

# knowledge_curator — every 2 hours
$action = New-ScheduledTaskAction -Execute $python -Argument "$runner knowledge_curator" -WorkingDirectory $workdir
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 2) -Once -At (Get-Date).Date
Register-ScheduledTask -TaskName "OpenJarvis-KnowledgeCurator" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host "Registered: OpenJarvis-KnowledgeCurator"

Write-Host "All operators registered."
