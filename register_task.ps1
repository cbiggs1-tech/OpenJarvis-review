$action = New-ScheduledTaskAction -Execute "C:\openjarvis\start_slack.bat"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName "OpenJarvis Slack Listener" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host "Task registered successfully."
