#Requires -Version 5.1
<#
.SYNOPSIS
  Advanced read-only desktop self-check for AI-agent analysis: inventory,
  system health diagnostics, and Reliability Monitor crash correlation.

.DESCRIPTION
  Collects (built-in Windows commands / WMI-CIM only - no RSAT, no modules, no admin):
    - Computer inventory: name, PRIMARY ip address (adapter whose
      "Connection-specific DNS Suffix" matches -PreferredDnsSuffix, else the
      adapter owning the best default route), all IPv4 addresses, manufacturer,
      model, serial, domain, BIOS, OS, architecture, install/boot time, uptime.
    - User information: login (console user, process-account fallback on
      servers), sessionType ('Local' = console desktop, 'RDP' = remote
      session), AD 'mail' via .NET DirectoryServices
      (UPN fallback; $null on workgroup), logon server, user DNS domain,
      password last-set / expiry date-time + days left (AD constructed attribute
      msDS-UserPasswordExpiryTimeComputed; WinNT ADSI fallback for local accounts).
    - Health checks: disk space/health (incl. SMART), memory, CPU, services,
      domain secure channel, gateway/DC reachability, firewall, BitLocker, TPM,
      Secure Boot, pending reboot, Windows Update, driver errors, event-log
      errors and unexpected shutdowns (default window: 14 days / -EventHours 336).
    - Reliability Monitor: the most recent Win32_ReliabilityRecords (app hangs,
      crashes, Windows failures), each correlated with Critical/Error/Warning
      events from the Application + System logs within +/- CorrelationSeconds
      (default 60s). Includes a daily TIMELINE: per-day failure/informational
      buckets in JSON (reliability.timeline) and an SVG time-line graph in the
      HTML report, similar to perfmon /rel.
      Messages are whitespace-normalized and truncated to -MessageMaxChars so
      the JSON stays compact and machine-parseable.
  Completely READ-ONLY - no changes are made to the system.
  All timestamps are local machine time, formatted 'yyyy-MM-dd HH:mm:ss'
  (timeline day buckets use 'yyyy-MM-dd').
  Prints exactly ONE single-line JSON object to stdout (agent-friendly contract):
    { status, host, generatedAt, durationMs, overall, score, counts,
      inventory, checks, reliability, remediation, reportFile, ... }
  Optionally writes a human-readable HTML report with -ReportPath.
  By default also opens the Reliability Monitor GUI (perfmon /rel = Control
  Panel > Security and Maintenance > Reliability Monitor); suppress with
  -NoReliabilityMonitor for headless/agent runs.
  Run elevated for maximum coverage; without elevation affected checks return SKIP/INFO.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Invoke-AdvancedDesktopSelfCheck.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -Command ".\Invoke-AdvancedDesktopSelfCheck.ps1 -ReportPath `$env:LOCALAPPDATA\Temp\selfcheck.html"
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Invoke-AdvancedDesktopSelfCheck.ps1 -ReliabilityCount 50 -CorrelationSeconds 180
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Invoke-AdvancedDesktopSelfCheck.ps1 -EventHours 168    # 7-day window / 7-day timeline
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Invoke-AdvancedDesktopSelfCheck.ps1 -NoReliabilityMonitor    # no GUI popup
  powershell -NoProfile -ExecutionPolicy Bypass -File .\Invoke-AdvancedDesktopSelfCheck.ps1 -PreferredDnsSuffix ""    # auto-detect via default route
#>
[CmdletBinding()]
param(
    [string]$ReportPath,
    [ValidateRange(1, 8760)][int]$EventHours = 336,   # 336 h = 14 days
    # ipconfig "Connection-specific DNS Suffix" of the corporate NIC; the
    # primary IP is taken from the matching adapter. Pass '' for pure auto mode.
    [string]$PreferredDnsSuffix = 'tvb-oa.tvb.org.hk',
    # Number of most recent Reliability Monitor records to collect.
    [ValidateRange(1, 200)][int]$ReliabilityCount = 30,
    # +/- seconds around each reliability record to pull correlated event logs.
    [ValidateRange(10, 600)][int]$CorrelationSeconds = 60,
    # Max correlated event-log entries kept per reliability record.
    [ValidateRange(1, 50)][int]$MaxEventsPerRecord = 10,
    # Truncation length for reliability / event messages in the JSON output.
    [ValidateRange(80, 2000)][int]$MessageMaxChars = 400,
    # Suppress the Reliability Monitor GUI (Control Panel > Security and
    # Maintenance > Reliability Monitor, i.e. perfmon /rel). By default the
    # window OPENS after collection; pass -NoReliabilityMonitor for headless /
    # agent runs. A [switch] is used deliberately: with powershell.exe -File,
    # arguments are literal strings, so value-taking [bool] params like
    # -ShowReliabilityMonitor:$false fail argument conversion.
    [switch]$NoReliabilityMonitor
)

$ErrorActionPreference = 'Stop'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$script:Checks = New-Object System.Collections.ArrayList

function Add-Check {
    param(
        [string]$Area,
        [string]$Name,
        [ValidateSet('PASS','WARN','FAIL','INFO','SKIP')][string]$Status,
        [string]$Detail,
        [string]$Recommendation = ''
    )
    $item = [ordered]@{ area = $Area; name = $Name; status = $Status; detail = ('' + $Detail).Trim() }
    if ($Recommendation) { $item['recommendation'] = $Recommendation }
    $null = $script:Checks.Add($item)
}

function FmtTime($d) {
    if ($null -eq $d) { return $null }
    return ([DateTime]$d).ToString('yyyy-MM-dd HH:mm:ss')
}

$out = [ordered]@{
    status      = 'error'
    host        = $env:COMPUTERNAME
    generatedAt = (FmtTime (Get-Date))
    durationMs  = 0
    overall     = 'unknown'
    score       = 0
    counts      = $null
    inventory   = $null
    checks      = $null
    reliability = $null
    remediation = $null
    reportFile  = $null
    reportError = $null
    relMonitorLaunched = $false
    relMonitorError    = $null
    message     = ''
}

function Emit-Result {
    param([string]$Message, [int]$Code = 0)
    $script:out.message    = $Message
    $script:out.durationMs = [int]$sw.ElapsedMilliseconds
    $script:out | ConvertTo-Json -Compress -Depth 12 | Write-Output
    exit $Code
}

function Clean([string]$s) {
    if ([string]::IsNullOrWhiteSpace($s)) { return '' }
    return (($s -replace '<[^>]+>', ' ' -replace '\s+', ' ').Trim())
}

function Trunc([string]$s, [int]$Max) {
    if ([string]::IsNullOrEmpty($s)) { return '' }
    $s = ($s -replace '\s+', ' ').Trim()
    if ($s.Length -gt $Max) { return $s.Substring(0, $Max) + '...[truncated]' }
    return $s
}

function Convert-AdsLargeInteger {
    param($Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [int64] -or $Value -is [int]) { return [int64]$Value }
    try {
        $high = [int64]$Value.GetType().InvokeMember('HighPart', [System.Reflection.BindingFlags]::GetProperty, $null, $Value, $null)
        $low  = [int64]$Value.GetType().InvokeMember('LowPart',  [System.Reflection.BindingFlags]::GetProperty, $null, $Value, $null)
        return ($high -shl 32) -bor ($low -band 0xFFFFFFFFL)
    } catch { return $null }
}

function Get-UserAccountInfo {
    param([string]$Account)
    $res = @{ email = $null; pwdLastSet = $null; passwordExpires = $null; neverExpires = $null; expiredNow = $false }
    if (-not $Account) { return $res }
    $sam = ($Account -split '\\')[-1]
    try {
        if ($env:USERDNSDOMAIN) {
            $esc = [regex]::Replace($sam, '([*()\\])', '\$1')
            Add-Type -AssemblyName System.DirectoryServices -ErrorAction Stop
            $sr = New-Object System.DirectoryServices.DirectorySearcher
            $sr.Filter = "(&(objectCategory=person)(objectClass=user)(sAMAccountName=$esc))"
            $null = $sr.PropertiesToLoad.AddRange(@('mail', 'userprincipalname', 'pwdlastset', 'useraccountcontrol', 'msds-userpasswordexpirytimecomputed'))
            $r = $sr.FindOne()
            if ($r) {
                $p = $r.Properties
                if ($p.Contains('mail') -and $p['mail'].Count) { $res.email = [string]$p['mail'][0] }
                elseif ($p.Contains('userprincipalname') -and $p['userprincipalname'].Count) {
                    $u = [string]$p['userprincipalname'][0]
                    if ($u -match '@') { $res.email = $u }
                }
                if ($p.Contains('useraccountcontrol') -and $p['useraccountcontrol'].Count) {
                    $res.neverExpires = (([int]$p['useraccountcontrol'][0]) -band 0x10000) -ne 0
                }
                if ($p.Contains('pwdlastset') -and $p['pwdlastset'].Count) {
                    $pls = Convert-AdsLargeInteger $p['pwdlastset'][0]
                    if ($pls -and $pls -gt 0) { $res.pwdLastSet = [DateTime]::FromFileTime($pls) }
                }
                if ($p.Contains('msds-userpasswordexpirytimecomputed') -and $p['msds-userpasswordexpirytimecomputed'].Count) {
                    $exp = Convert-AdsLargeInteger $p['msds-userpasswordexpirytimecomputed'][0]
                    if ($null -ne $exp) {
                        if ($exp -eq [int64]::MaxValue) { $res.neverExpires = $true }
                        elseif ($exp -eq 0) { $res.expiredNow = $true; $res.neverExpires = $false }
                        else { $res.passwordExpires = [DateTime]::FromFileTime($exp); $res.neverExpires = $false }
                    }
                }
            }
        } else {
            $u = [ADSI]("WinNT://$env:COMPUTERNAME/$sam,user")
            $flags = [int]$u.UserFlags.Value
            $res.neverExpires = ($flags -band 0x10000) -ne 0
            if (-not $res.neverExpires) {
                try { $res.passwordExpires = [DateTime]$u.PasswordExpirationDate.Value } catch { }
            }
        }
    } catch { }
    return $res
}

function Get-PrimaryIPv4 {
    param([string]$PreferredDnsSuffix)
    $res = @{ ip = $null; suffix = $null; gw = $null }
    try {
        $cfgs = @(Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True' |
                  Where-Object { $_.IPAddress })
        if (-not $cfgs.Count) { return $res }
        $dnsByIf = @{}
        try {
            foreach ($d in @(Get-DnsClient -ErrorAction SilentlyContinue)) {
                $ix = [string]$d.InterfaceIndex
                $s  = ('' + $d.ConnectionSpecificSuffix).Trim().TrimEnd('.')
                if ($s -and -not $dnsByIf.ContainsKey($ix)) { $dnsByIf[$ix] = $s }
            }
        } catch { }
        $best = $null
        if ($PreferredDnsSuffix) {
            $p = $PreferredDnsSuffix.Trim().TrimEnd('.')
            if ($p) {
                $best = $cfgs | Where-Object {
                    $ix = [string]$_.InterfaceIndex
                    $wmiSuffix = ('' + $_.DnsSuffix).Trim().TrimEnd('.')
                    (($dnsByIf.ContainsKey($ix) -and $dnsByIf[$ix] -eq $p) -or ($wmiSuffix -eq $p))
                } | Select-Object -First 1
            }
        }
        if (-not $best) {
            try {
                $ifMet = @{}
                foreach ($i in @(Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue)) {
                    $ifMet[[string]$i.InterfaceIndex] = [int]$i.InterfaceMetric
                }
                $bestRoute = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue) |
                    Sort-Object @{ Expression = {
                        $idx = [string] $_.InterfaceIndex
                        $m = 9999
                        if ($ifMet.ContainsKey($idx)) { $m = $ifMet[$idx] }
                        $m * 1000 + [int] $_.RouteMetric
                    } } | Select-Object -First 1
                if ($bestRoute) {
                    $best = $cfgs | Where-Object { $_.InterfaceIndex -eq $bestRoute.InterfaceIndex } | Select-Object -First 1
                }
            } catch { }
        }
        if (-not $best) { $best = $cfgs | Where-Object { $_.DefaultIPGateway } | Select-Object -First 1 }
        if (-not $best) { $best = $cfgs[0] }
        if ($best) {
            $ixb = [string]$best.InterfaceIndex
            if ($dnsByIf.ContainsKey($ixb)) { $res.suffix = $dnsByIf[$ixb] } else { $res.suffix = ('' + $best.DnsSuffix).Trim() }
            $res.ip = $best.IPAddress | Where-Object { $_ -match '^(\d{1,3}\.){3}\d{1,3}$' -and $_ -notmatch '^169\.' } | Select-Object -First 1
            $gws = @($best.DefaultIPGateway)
            if ($gws.Count) { $res.gw = [string]$gws[0] }
        }
    } catch { }
    return $res
}

function Enc([string]$s) {
    if ($null -eq $s) { return '' }
    return [System.Net.WebUtility]::HtmlEncode($s)
}

function Fmt($v) {
    if ($null -eq $v) { return '' }
    if ($v -is [System.Collections.IDictionary]) {
        return (($v.GetEnumerator() | ForEach-Object { "$($_.Key)=$(Fmt $_.Value)" }) -join ', ')
    }
    if ($v -isnot [string] -and $v -is [System.Collections.IEnumerable]) {
        return (($v | ForEach-Object { Fmt $_ }) -join '; ')
    }
    return [string]$v
}

function Write-HtmlReport {
    param([string]$Path)
    $colorMap = @{ PASS = '#1a7f37'; WARN = '#9a6700'; FAIL = '#c62828'; INFO = '#0b5394'; SKIP = '#666666' }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('<!DOCTYPE html><html><head><meta charset="utf-8">')
    [void]$sb.AppendLine('<title>Desktop Self-Check - ' + (Enc $out.host) + '</title><style>')
    [void]$sb.AppendLine('body{font-family:"Segoe UI",Arial,sans-serif;margin:24px;color:#222}')
    [void]$sb.AppendLine('table{border-collapse:collapse;margin:8px 0 20px}td,th{border:1px solid #ccc;padding:4px 10px;font-size:13px;text-align:left}th{background:#f2f2f2}')
    [void]$sb.AppendLine('h1{font-size:20px}h2{font-size:15px;margin:18px 0 4px}.badge{font-size:18px;font-weight:bold}')
    [void]$sb.AppendLine('details{margin:4px 0}summary{cursor:pointer;font-size:12px;color:#0b5394}')
    [void]$sb.AppendLine('</style></head><body>')
    [void]$sb.AppendLine('<h1>Desktop Self-Check: ' + (Enc $out.host) + ' - ' + (Enc $out.generatedAt) + '</h1>')
    $c = $out.counts
    [void]$sb.AppendLine('<p class="badge" style="color:' + $colorMap[$out.overall.ToUpper()] + '">Overall: ' + (Enc $out.overall) + ' - score ' + $out.score + '/100</p>')
    [void]$sb.AppendLine('<p>pass ' + $c.pass + ' | warn ' + $c.warn + ' | fail ' + $c.fail + ' | info ' + $c.info + ' | skip ' + $c.skip + '</p>')
    foreach ($k in $out.inventory.Keys) {
        [void]$sb.AppendLine('<h2>' + (Enc $k) + '</h2><table><tr><th>Property</th><th>Value</th></tr>')
        $v = $out.inventory[$k]
        if ($v -is [System.Collections.IDictionary]) {
            foreach ($p in $v.GetEnumerator()) {
                [void]$sb.AppendLine('<tr><td>' + (Enc ([string]$p.Key)) + '</td><td>' + (Enc (Fmt $p.Value)) + '</td></tr>')
            }
        }
        [void]$sb.AppendLine('</table>')
    }
    [void]$sb.AppendLine('<h2>Health checks</h2><table><tr><th>Area</th><th>Check</th><th>Status</th><th>Detail</th></tr>')
    foreach ($chk in $out.checks) {
        $col = $colorMap[$chk.status]
        [void]$sb.AppendLine('<tr><td>' + (Enc $chk.area) + '</td><td>' + (Enc $chk.name) + '</td><td style="color:' + $col + ';font-weight:bold">' + (Enc $chk.status) + '</td><td>' + (Enc $chk.detail) + '</td></tr>')
    }
    [void]$sb.AppendLine('</table>')
    if ($out.reliability -and $out.reliability.available) {
        $rs = $out.reliability.summary
        [void]$sb.AppendLine('<h2>Reliability Monitor - recent failures</h2>')
        [void]$sb.AppendLine('<p>' + $out.reliability.recordCount + ' record(s); last 24h: ' + $rs.failuresLast24h + '; last 7d: ' + $rs.failuresLast7d + '; top products: ' + (Enc ($rs.topProducts -join '; ')) + '</p>')
        $tl = @($out.reliability.timeline)
        if ($tl.Count) {
            $w = 940; $h = 250; $ml = 40; $mr = 10; $mt = 26; $mb = 40
            $pw = $w - $ml - $mr; $ph = $h - $mt - $mb
            $n = $tl.Count
            $colW = [int]($pw / $n)
            $barW = [int]($colW * 0.6); if ($barW -lt 4) { $barW = 4 }
            $max = 4
            foreach ($b in $tl) { $t = $b.failures + $b.informational; if ($t -gt $max) { $max = $t } }
            $step = 1; if ($max -gt 8) { $step = [int][Math]::Ceiling($max / 4) }
            [void]$sb.AppendLine('<h2>Reliability time-line - last ' + $n + ' day(s)</h2>')
            [void]$sb.AppendLine('<svg width="' + $w + '" height="' + $h + '" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI,Arial,sans-serif">')
            [void]$sb.AppendLine('<rect x="' + $ml + '" y="4" width="10" height="10" fill="#c62828"/><text x="' + ($ml + 14) + '" y="13" font-size="11" fill="#333">App/Windows failure</text>')
            [void]$sb.AppendLine('<rect x="' + ($ml + 160) + '" y="4" width="10" height="10" fill="#0b5394"/><text x="' + ($ml + 174) + '" y="13" font-size="11" fill="#333">Installer / informational</text>')
            for ($v = 0; $v -le $max; $v += $step) {
                $y = $mt + $ph - [int]($v * $ph / $max)
                [void]$sb.AppendLine('<line x1="' + $ml + '" y1="' + $y + '" x2="' + ($w - $mr) + '" y2="' + $y + '" stroke="#e8e8e8"/>')
                [void]$sb.AppendLine('<text x="' + ($ml - 6) + '" y="' + ($y + 4) + '" font-size="10" fill="#666" text-anchor="end">' + $v + '</text>')
            }
            for ($i = 0; $i -lt $n; $i++) {
                $b = $tl[$i]
                $x = $ml + $i * $colW + [int](($colW - $barW) / 2)
                $hf = [int]($b.failures * $ph / $max)
                $hi = [int]($b.informational * $ph / $max)
                $yf = $mt + $ph - $hf
                $yi = $yf - $hi
                $tot = $b.failures + $b.informational
                $tip = Enc ($b.date + ': ' + $b.failures + ' failure(s), ' + $b.informational + ' informational' + $(if ($b.products.Count) { ' | ' + ($b.products -join '; ') } else { '' }))
                if ($hf -gt 0) { [void]$sb.AppendLine('<rect x="' + $x + '" y="' + $yf + '" width="' + $barW + '" height="' + $hf + '" fill="#c62828"><title>' + $tip + '</title></rect>') }
                if ($hi -gt 0) { [void]$sb.AppendLine('<rect x="' + $x + '" y="' + $yi + '" width="' + $barW + '" height="' + $hi + '" fill="#0b5394"><title>' + $tip + '</title></rect>') }
                if ($tot -gt 0) {
                    [void]$sb.AppendLine('<text x="' + ($x + [int]($barW / 2)) + '" y="' + ($yi - 4) + '" font-size="10" fill="#333" text-anchor="middle">' + $tot + '</text>')
                }
                $lbl = ([datetime]::ParseExact($b.date, 'yyyy-MM-dd', [System.Globalization.CultureInfo]::InvariantCulture)).ToString('MM-dd')
                $lx = $ml + $i * $colW + [int]($colW / 2)
                [void]$sb.AppendLine('<text x="' + $lx + '" y="' + ($mt + $ph + 16) + '" font-size="9" fill="#666" text-anchor="middle">' + $lbl + '</text>')
            }
            [void]$sb.AppendLine('<line x1="' + $ml + '" y1="' + ($mt + $ph) + '" x2="' + ($w - $mr) + '" y2="' + ($mt + $ph) + '" stroke="#999"/>')
            [void]$sb.AppendLine('<line x1="' + $ml + '" y1="' + $mt + '" x2="' + $ml + '" y2="' + ($mt + $ph) + '" stroke="#999"/>')
            [void]$sb.AppendLine('</svg>')
        }
        [void]$sb.AppendLine('<table><tr><th>Time</th><th>Source</th><th>Product</th><th>Event ID</th><th>Message</th><th>Correlated events (+/-' + $CorrelationSeconds + 's)</th></tr>')
        foreach ($r in $out.reliability.records) {
            $corrHtml = ''
            foreach ($e in @($r.correlatedEvents)) {
                $corrHtml += '<div><b>' + (Enc ([string]$e.time)) + '</b> [' + (Enc $e.log) + '] ' + (Enc $e.provider) + ' id=' + $e.id + ' (' + (Enc $e.level) + '): ' + (Enc $e.message) + '</div>'
            }
            if (-not $corrHtml) { $corrHtml = '<i>none</i>' }
            [void]$sb.AppendLine('<tr><td>' + (Enc ([string]$r.time)) + '</td><td>' + (Enc $r.source) + '</td><td>' + (Enc $r.product) + '</td><td>' + $r.eventId + '</td><td>' + (Enc $r.message) + '</td><td><details><summary>' + $r.correlatedEventCount + ' event(s)</summary>' + $corrHtml + '</details></td></tr>')
        }
        [void]$sb.AppendLine('</table>')
    }
    if (@($out.remediation).Count) {
        [void]$sb.AppendLine('<h2>Recommended actions</h2><ul>')
        foreach ($r in $out.remediation) { [void]$sb.AppendLine('<li>' + (Enc $r) + '</li>') }
        [void]$sb.AppendLine('</ul>')
    }
    [void]$sb.AppendLine('<p style="color:#888;font-size:11px">Generated by Invoke-AdvancedDesktopSelfCheck (windows-desktop-selfcheck). Read-only: no system changes were made.</p>')
    [void]$sb.AppendLine('</body></html>')
    Set-Content -Path $Path -Value $sb.ToString() -Encoding UTF8
}
try {
    $os   = Get-CimInstance -ClassName Win32_OperatingSystem
    $cs   = Get-CimInstance -ClassName Win32_ComputerSystem
    $bios = Get-CimInstance -ClassName Win32_BIOS
    $cpuC = @(Get-CimInstance -ClassName Win32_Processor)
    $cpu  = $cpuC[0]
    $uptime = (Get-Date) - $os.LastBootUpTime
    $ipList = @()
    try {
        $ipList = @(Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True' |
            ForEach-Object { $_.IPAddress } | Where-Object { $_ -match '^(\d{1,3}\.){3}\d{1,3}$' -and $_ -notmatch '^169\.' } |
            Select-Object -Unique)
    } catch { }
    $primNet = Get-PrimaryIPv4 -PreferredDnsSuffix $PreferredDnsSuffix
    $invComputer = [ordered]@{
        name           = $cs.Name
        ipAddress      = $primNet.ip
        ipDnsSuffix    = $primNet.suffix
        defaultGateway = $primNet.gw
        ipAddresses    = $ipList
        manufacturer   = $cs.Manufacturer
        model          = $cs.Model
        serialNumber   = $bios.SerialNumber
        domain         = $cs.Domain
        biosVersion    = [string]$bios.SMBIOSBIOSVersion
        os             = (Clean $os.Caption)
        osVersion      = "$($os.Version) (Build $($os.BuildNumber))"
        architecture   = $os.OSArchitecture
        installDate    = (FmtTime $os.InstallDate)
        lastBoot       = (FmtTime $os.LastBootUpTime)
        uptimeHours    = [Math]::Round($uptime.TotalHours, 1)
    }
    $loginName = ('' + $cs.UserName).Trim()
    if (-not $loginName) { $loginName = "$env:USERDOMAIN\$env:USERNAME" }
    $acct = Get-UserAccountInfo -Account $loginName
    $pwdDaysLeft = $null
    if ($acct.passwordExpires) { $pwdDaysLeft = [Math]::Round(($acct.passwordExpires - (Get-Date)).TotalDays, 1) }
    $sessionName = ('' + $env:SESSIONNAME).Trim()
    $sessionId = $null
    try { $sessionId = (Get-Process -Id $PID).SessionId } catch { }
    $consoleSessionId = $null
    $consoleIdSource = 'none'
    try { Add-Type -Namespace Win32 -Name ConsoleSession -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint WTSGetActiveConsoleSessionId();' -ErrorAction SilentlyContinue } catch { }
    try {
        $csid = [Win32.ConsoleSession]::WTSGetActiveConsoleSessionId()
        if ($csid -ne 0xFFFFFFFF) { $consoleSessionId = [int]$csid; $consoleIdSource = 'kernel32' }
    } catch { }
    if ($null -eq $consoleSessionId) {
        try {
            foreach ($ln in @(qwinsta 2>$null)) {
                $tok = (('' + $ln) -replace '^\s*>', '').Trim() -split '\s+'
                if ($tok[0] -eq 'console') {
                    foreach ($t in $tok) { if ($t -match '^\d+$') { $consoleSessionId = [int]$t; $consoleIdSource = 'qwinsta'; break } }
                    if ($null -ne $consoleSessionId) { break }
                }
            }
        } catch { }
    }
    $isLocal = ($sessionName -eq 'Console') -or ($null -ne $consoleSessionId -and $null -ne $sessionId -and $sessionId -eq $consoleSessionId)
    $sessionType = $(if ($isLocal) { 'Local' } else { 'RDP' })
    Add-Check -Area 'User' -Name 'SessionType' -Status 'INFO' -Detail "sessionType=$sessionType (SESSIONNAME='$sessionName', processSession=$sessionId, consoleSession=$consoleSessionId via $consoleIdSource)"
    $invUser = [ordered]@{
        login                = $loginName
        sessionType          = $sessionType
        email                = $acct.email
        logonServer          = $env:LOGONSERVER
        userDnsDomain        = $env:USERDNSDOMAIN
        passwordLastSet      = (FmtTime $acct.pwdLastSet)
        passwordExpires      = (FmtTime $acct.passwordExpires)
        passwordNeverExpires = $(if ($null -eq $acct.neverExpires) { 'Unknown' } elseif ($acct.neverExpires) { 'Yes' } else { 'No' })
        passwordDaysLeft     = $pwdDaysLeft
    }
    if ($acct.neverExpires) {
        Add-Check -Area 'Security' -Name 'PasswordExpiry' -Status 'INFO' -Detail 'Account password is set to never expire (policy or flag)'
    } elseif ($acct.expiredNow -or ($null -ne $pwdDaysLeft -and $pwdDaysLeft -le 0)) {
        Add-Check -Area 'Security' -Name 'PasswordExpiry' -Status 'WARN' -Detail $(if ($acct.expiredNow) { 'Password expired / must change at next logon' } else { "Password expired $([Math]::Abs($pwdDaysLeft)) day(s) ago ($(FmtTime $acct.passwordExpires))" }) -Recommendation 'Change the domain password now: Ctrl+Alt+Del > Change a password.'
    } elseif ($null -ne $pwdDaysLeft -and $pwdDaysLeft -le 7) {
        Add-Check -Area 'Security' -Name 'PasswordExpiry' -Status 'WARN' -Detail "Password expires in $pwdDaysLeft day(s) ($(FmtTime $acct.passwordExpires))" -Recommendation 'Change the password before expiry: Ctrl+Alt+Del > Change a password; update saved credentials on mobile/VPN afterwards.'
    } elseif ($null -ne $pwdDaysLeft) {
        Add-Check -Area 'Security' -Name 'PasswordExpiry' -Status 'PASS' -Detail "Password expires $(FmtTime $acct.passwordExpires) ($pwdDaysLeft day(s) left)"
    } else {
        Add-Check -Area 'Security' -Name 'PasswordExpiry' -Status 'SKIP' -Detail 'Password expiry not readable (local account without policy, DC unreachable, or attribute not returned)'
    }
    $totalBytes = [int64]$cs.TotalPhysicalMemory
    $freeKB     = [int64]$os.FreePhysicalMemory
    $ramUsedPct = if ($totalBytes -gt 0) { [Math]::Round((1 - ($freeKB * 1KB) / $totalBytes) * 100, 1) } else { 0 }
    Add-Check -Area 'Resources' -Name 'Memory' -Status $(if ($ramUsedPct -gt 92) { 'WARN' } else { 'PASS' }) -Detail ('RAM {0} GB total, {1} GB free, {2}% used' -f [Math]::Round($totalBytes / 1GB, 1), [Math]::Round(($freeKB * 1KB) / 1GB, 1), $ramUsedPct) -Recommendation $(if ($ramUsedPct -gt 92) { 'Check top processes in inventory.runtime.topProcesses; close unused apps / reboot if chronic.' } else { '' })
    $cpuLoad = $null
    if ($null -ne $cpu.LoadPercentage) { $cpuLoad = [int](($cpuC | Measure-Object LoadPercentage -Average).Average) }
    Add-Check -Area 'Resources' -Name 'CPU' -Status $(if ($null -eq $cpuLoad) { 'SKIP' } elseif ($cpuLoad -ge 95) { 'WARN' } else { 'PASS' }) -Detail "$($cpu.Name) | $($cpu.NumberOfCores) cores / $($cpu.NumberOfLogicalProcessors) threads | instant load ${cpuLoad}%"
    try {
        $ldC = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='C:'"
        $cFreePct = if ($ldC.Size -gt 0) { [Math]::Round($ldC.FreeSpace / $ldC.Size * 100, 1) } else { 0 }
        $cSt = if ($cFreePct -lt 5) { 'FAIL' } elseif ($cFreePct -lt 10) { 'WARN' } else { 'PASS' }
        Add-Check -Area 'Disk' -Name 'FreeSpaceC' -Status $cSt -Detail ('C: {0} GB free ({1}%)' -f [Math]::Round($ldC.FreeSpace / 1GB, 1), $cFreePct) -Recommendation $(if ($cSt -ne 'PASS') { 'Run Disk Cleanup / cleanmgr or Storage Sense, clear %TEMP%, Downloads, and old Windows Update files.' } else { '' })
    } catch { Add-Check -Area 'Disk' -Name 'FreeSpaceC' -Status 'SKIP' -Detail $_.Exception.Message }
    $volsTxt = 'n/a'
    $badVolCount = 0
    try {
        $vols = @(Get-Volume -ErrorAction Stop | Where-Object { $_.DriveType -eq 'Fixed' -and $_.DriveLetter })
        $badVols = @($vols | Where-Object { "$($_.HealthStatus)" -ne 'Healthy' })
        $badVolCount = $badVols.Count
        $volsTxt = ($vols | ForEach-Object { "$($_.DriveLetter): $([Math]::Round($_.Size/1GB)) GB, $($_.HealthStatus)" }) -join '; '
        Add-Check -Area 'Disk' -Name 'VolumeHealth' -Status $(if ($badVolCount) { 'FAIL' } else { 'PASS' }) -Detail $(if ($badVolCount) { (($badVols | ForEach-Object { "$($_.DriveLetter):=$($_.HealthStatus)/$($_.OperationalStatus)" }) -join '; ') + " | all: $volsTxt" } else { "All $($vols.Count) fixed volumes Healthy | $volsTxt" }) -Recommendation $(if ($badVolCount) { 'Back up immediately; run chkdsk C: /scan (admin) and repair.' } else { '' })
    } catch { Add-Check -Area 'Disk' -Name 'VolumeHealth' -Status 'SKIP' -Detail 'Get-Volume unavailable' }
    $pdsk = @()
    try {
        $pdsk = @(Get-PhysicalDisk -ErrorAction Stop)
        $badPdsk = @($pdsk | Where-Object { "$($_.HealthStatus)" -ne 'Healthy' -or ("$($_.OperationalStatus)" -ne 'OK' -and "$($_.OperationalStatus)") })
        $pdskTxt = ($pdsk | ForEach-Object { "$($_.FriendlyName) [$($_.MediaType), $([Math]::Round($_.Size/1GB)) GB, $($_.BusType)] = $($_.HealthStatus)/$($_.OperationalStatus)" }) -join '; '
        Add-Check -Area 'Disk' -Name 'PhysicalDiskHealth' -Status $(if ($badPdsk.Count) { 'FAIL' } else { 'PASS' }) -Detail $pdskTxt -Recommendation $(if ($badPdsk.Count) { 'SMART/physical disk degraded: back up now, check cabling/temperature, plan replacement.' } else { '' })
    } catch { Add-Check -Area 'Disk' -Name 'PhysicalDiskHealth' -Status 'SKIP' -Detail 'Get-PhysicalDisk unavailable (VM or unsupported storage provider)' }
    if ($uptime.TotalDays -gt 30) {
        Add-Check -Area 'System' -Name 'Uptime' -Status 'WARN' -Detail ("Uptime {0:N1} days - reboot recommended (updates/leak reset)" -f $uptime.TotalDays)
    } else {
        Add-Check -Area 'System' -Name 'Uptime' -Status 'PASS' -Detail ("Uptime {0:N1} days" -f $uptime.TotalDays)
    }
    $invHardware = [ordered]@{
        cpu   = $cpu.Name
        cores = $cpuC | ForEach-Object { $_.NumberOfCores } | Measure-Object -Sum | ForEach-Object Sum
        ramGB = [Math]::Round($totalBytes / 1GB, 1)
        disks = @($pdsk | ForEach-Object { [ordered]@{ name = $_.FriendlyName; type = $_.MediaType; sizeGB = [Math]::Round($_.Size / 1GB) } })
    }
    try {
        $batt = Get-CimInstance -ClassName Win32_Battery -ErrorAction Stop | Select-Object -First 1
        if ($batt) {
            $invHardware['battery'] = [ordered]@{ chargePct = $batt.EstimatedChargeRemaining; statusCode = $batt.BatteryStatus }
            if ($batt.EstimatedChargeRemaining -lt 15 -and $batt.BatteryStatus -ne 2) {
                Add-Check -Area 'Power' -Name 'Battery' -Status 'WARN' -Detail "Battery at $($batt.EstimatedChargeRemaining)% and not on AC" -Recommendation 'Connect the power adapter; check battery health.'
            } else {
                Add-Check -Area 'Power' -Name 'Battery' -Status 'PASS' -Detail "Battery $($batt.EstimatedChargeRemaining)% (status $($batt.BatteryStatus), 2=charging/AC)"
            }
        }
    } catch { Add-Check -Area 'Power' -Name 'Battery' -Status 'INFO' -Detail 'No battery detected (desktop or unsupported)' }
    $domainJoined = ($env:USERDOMAIN -ne $env:COMPUTERNAME)
    if ($domainJoined -and $env:USERDNSDOMAIN) {
        try {
            if (Test-ComputerSecureChannel) { Add-Check -Area 'Network' -Name 'SecureChannel' -Status 'PASS' -Detail "Machine trust with $env:USERDNSDOMAIN OK" }
            else { Add-Check -Area 'Network' -Name 'SecureChannel' -Status 'FAIL' -Detail 'Secure channel BROKEN - login/GPO/updates will fail' -Recommendation 'Re-establish trust (admin, domain creds): Reset-ComputerSecureChannel -Repair -Credential <domain\admin>' }
        } catch { Add-Check -Area 'Network' -Name 'SecureChannel' -Status 'WARN' -Detail "Secure channel test failed: $($_.Exception.Message)" }
        try {
            $dcIp = ([System.Net.Dns]::GetHostAddresses($env:USERDNSDOMAIN))[0]
            if (Test-Connection -ComputerName $dcIp -Count 2 -Quiet -ErrorAction SilentlyContinue) { Add-Check -Area 'Network' -Name 'ReachDC' -Status 'PASS' -Detail "Domain reachable via $dcIp" }
            else { Add-Check -Area 'Network' -Name 'ReachDC' -Status 'WARN' -Detail "$($env:USERDNSDOMAIN) not answering ping from $dcIp (ICMP may be firewalled)" }
        } catch { Add-Check -Area 'Network' -Name 'ReachDC' -Status 'SKIP' -Detail $_.Exception.Message }
    } else {
        Add-Check -Area 'Network' -Name 'SecureChannel' -Status 'INFO' -Detail 'Workgroup-joined machine; domain trust checks skipped'
    }
    try {
        $adapters = @(Get-CimInstance -ClassName Win32_NetworkAdapter -Filter 'PhysicalAdapter=True AND NetEnabled=True')
        if ($adapters.Count -eq 0) {
            Add-Check -Area 'Network' -Name 'Interfaces' -Status 'FAIL' -Detail 'No connected physical network adapter' -Recommendation 'Check cable/Wi-Fi, enable adapter in ncpa.cpl, reinstall NIC driver.'
        } else {
            $adTxt = ($adapters | ForEach-Object { "$($_.Name) @ $([Math]::Round($_.Speed / 1MB)) Mbps" }) -join '; '
            Add-Check -Area 'Network' -Name 'Interfaces' -Status 'PASS' -Detail $adTxt
            if ($primNet.gw) {
                $gw = $primNet.gw
                $gwOk = Test-Connection -ComputerName $gw -Count 1 -Quiet -ErrorAction SilentlyContinue
                Add-Check -Area 'Network' -Name 'Gateway' -Status $(if ($gwOk) { 'PASS' } else { 'WARN' }) -Detail "Gateway $gw on adapter '$($primNet.suffix)' / source IP $($primNet.ip)" -Recommendation $(if (-not $gwOk) { 'Gateway unreachable: reload adapter (Disable/Enable), renew DHCP (ipconfig /release /renew), check switch port/AP.' } else { '' })
            }
        }
    } catch { Add-Check -Area 'Network' -Name 'Interfaces' -Status 'SKIP' -Detail $_.Exception.Message }
    try {
        $fwp = @(Get-NetFirewallProfile -ErrorAction Stop)
        $fwOff = @($fwp | Where-Object { "$($_.Enabled)" -ne 'True' -and $_.Name -ne 'Public' })
        Add-Check -Area 'Security' -Name 'Firewall' -Status $(if ($fwOff.Count) { 'FAIL' } else { 'PASS' }) -Detail $(if ($fwOff.Count) { 'Enabled=False on: ' + (($fwOff | ForEach-Object { $_.Name }) -join ', ') } else { 'Domain/Private/Public firewall profiles enabled' })
    } catch {
        try {
            $mp = Get-Service -Name MpsSvc -ErrorAction Stop
            Add-Check -Area 'Security' -Name 'Firewall' -Status $(if ($mp.Status -eq 'Running') { 'PASS' } else { 'FAIL' }) -Detail "MpsSvc $($mp.Status) (per-profile state needs elevation)"
        } catch { Add-Check -Area 'Security' -Name 'Firewall' -Status 'SKIP' -Detail 'Firewall state not readable' }
    }
    try {
        $blv = @(Get-BitLockerVolume -ErrorAction Stop)
        $off = @($blv | Where-Object { "$($_.ProtectionStatus)" -eq 'Off' })
        Add-Check -Area 'Security' -Name 'BitLocker' -Status $(if ($off.Count) { 'WARN' } else { 'PASS' }) -Detail $(if ($off.Count) { 'Protection OFF: ' + (($off | ForEach-Object { "$($_.MountPoint)[$($_.VolumeType)]" }) -join ', ') } else { 'All volumes with BitLocker protected' }) -Recommendation $(if ($off.Count) { 'Enable-BitLocker -MountPoint <drv> -RecoveryPasswordProtector (run elevated; escrow recovery key to AD).' } else { '' })
    } catch { Add-Check -Area 'Security' -Name 'BitLocker' -Status 'SKIP' -Detail 'BitLocker check unavailable (needs elevation, or Home edition)' }
    try {
        if (Confirm-SecureBootUEFI) { Add-Check -Area 'Security' -Name 'SecureBoot' -Status 'PASS' -Detail 'Secure Boot enabled' }
        else { Add-Check -Area 'Security' -Name 'SecureBoot' -Status 'WARN' -Detail 'Secure Boot disabled' -Recommendation 'Enable Secure Boot in UEFI/BIOS setup.' }
    } catch { Add-Check -Area 'Security' -Name 'SecureBoot' -Status 'SKIP' -Detail 'Secure Boot check unavailable (legacy BIOS or needs elevation)' }
    try {
        $tpm = Get-Tpm -ErrorAction Stop
        Add-Check -Area 'Security' -Name 'TPM' -Status $(if ($tpm.TpmPresent) { 'PASS' } else { 'INFO' }) -Detail "TPM present=$($tpm.TpmPresent) ready=$($tpm.TpmReady) owned=$($tpm.TpmOwned)"
    } catch { Add-Check -Area 'Security' -Name 'TPM' -Status 'SKIP' -Detail 'TPM check unavailable' }
    try {
        $excl = @('MapsBroker', 'lfsvc', 'WMPNetworkSvc', 'dmwappushservice', 'RetailDemo', 'WSearch')
        $autoStopped = @(Get-CimInstance -ClassName Win32_Service -Filter "StartMode='Auto' AND State='Stopped'" | Where-Object { $excl -notcontains $_.Name })
        if ($autoStopped.Count) {
            Add-Check -Area 'Services' -Name 'AutoStartStopped' -Status 'WARN' -Detail ("Auto-start services not running: " + (($autoStopped | Select-Object -First 8 | ForEach-Object { $_.Name }) -join ', ') + " (total $($autoStopped.Count))") -Recommendation 'Restart required services (Start-Service <name> -Elevated); set genuinely optional ones to Manual; check service logon/GPO errors.'
        } else {
            Add-Check -Area 'Services' -Name 'AutoStartStopped' -Status 'PASS' -Detail 'No unexpected stopped auto-start services'
        }
    } catch { Add-Check -Area 'Services' -Name 'AutoStartStopped' -Status 'SKIP' -Detail $_.Exception.Message }
    $rebootReasons = @()
    try {
        if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') { $rebootReasons += 'CBS RebootPending' }
        if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') { $rebootReasons += 'WU RebootRequired' }
        $pfro = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name PendingFileRenameOperations -ErrorAction SilentlyContinue).PendingFileRenameOperations
        if ($pfro) { $rebootReasons += 'PendingFileRenameOperations' }
        $wr = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control' -Name 'Windows System Automatic Reboot Required' -ErrorAction SilentlyContinue).'Windows System Automatic Reboot Required'
        if ($wr) { $rebootReasons += 'WindowsSystemRebootRequired' }
    } catch { }
    Add-Check -Area 'System' -Name 'PendingReboot' -Status $(if ($rebootReasons.Count) { 'WARN' } else { 'PASS' }) -Detail $(if ($rebootReasons.Count) { 'Reboot pending (' + ($rebootReasons -join '; ') + ')' } else { 'No reboot pending' }) -Recommendation $(if ($rebootReasons.Count) { 'Reboot the machine within the next maintenance window.' } else { '' })
    try {
        $wu     = New-Object -ComObject Microsoft.Update.Session
        $srch   = $wu.CreateUpdateSearcher()
        $pend   = $srch.Search('IsInstalled=0 and IsHidden=0')
        $his    = $null
        try { $hist = $srch.QueryHistory(0, 1); if ($hist.Count) { $his = $hist[0].Date } } catch { }
        $pendingCount = $pend.Updates.Count
        $titles = ''
        if ($pendingCount) { $titles = ($pend.Updates | Select-Object -First 5 | ForEach-Object { $_.Title }) -join '; ' }
        $stale = ($null -ne $his -and ((Get-Date) - $his).TotalDays -gt 30)
        $st = if ($pendingCount -and $stale) { 'WARN' } elseif ($pendingCount) { 'INFO' } else { 'PASS' }
        $det = "$pendingCount update(s) pending install"
        if ($his) { $det += "; last install $(FmtTime $his)" } else { $det += '; no update history visible' }
        Add-Check -Area 'Updates' -Name 'WindowsUpdate' -Status $st -Detail $det -Recommendation $(if ($st -ne 'PASS') { "Pending: $titles" } else { '' })
    } catch { Add-Check -Area 'Updates' -Name 'WindowsUpdate' -Status 'SKIP' -Detail "Windows Update COM not queryable: $($_.Exception.Message)" }
    try {
        $badDev = @(Get-CimInstance -ClassName Win32_PnPEntity -Filter 'ConfigManagerErrorCode <> 0')
        if ($badDev.Count) {
            Add-Check -Area 'System' -Name 'FaultyDevices' -Status 'WARN' -Detail (($badDev | Select-Object -First 5 | ForEach-Object { "$($_.Name) (err $($_.ConfigManagerErrorCode))" }) -join '; ') -Recommendation 'Review in Device Manager: update/reinstall drivers, remove phantom (non-present) devices.'
        } else {
            Add-Check -Area 'System' -Name 'FaultyDevices' -Status 'PASS' -Detail 'No devices with driver errors'
        }
    } catch { Add-Check -Area 'System' -Name 'FaultyDevices' -Status 'SKIP' -Detail $_.Exception.Message }
    foreach ($log in @('System', 'Application')) {
        try {
            $since = (Get-Date).AddHours(-$EventHours)
            $evts = @(Get-WinEvent -FilterHashtable @{ LogName = $log; Level = 1, 2; StartTime = $since } -ErrorAction SilentlyContinue)
            $crit = @($evts | Where-Object { $_.Level -eq 1 })
            $byProv = ($evts | Group-Object ProviderName | Sort-Object Count -Descending | Select-Object -First 4 | ForEach-Object { "$($_.Name) x$($_.Count)" }) -join ', '
            $st = if ($crit.Count -gt 0 -or $evts.Count -gt 50) { 'WARN' } elseif ($evts.Count -gt 5) { 'INFO' } else { 'PASS' }
            Add-Check -Area 'EventLog' -Name "Errors-$log" -Status $st -Detail "$($evts.Count) error/critical events in last ${EventHours}h (critical: $($crit.Count)); top providers: $(if ($byProv) { $byProv } else { 'none' })"
            $dirty = @($evts | Where-Object { $_.Id -in @(41, 6008) -and $_.ProviderName -in @('Microsoft-Windows-Kernel-Power', 'EventLog') })
            if ($dirty.Count) {
                Add-Check -Area 'EventLog' -Name 'UnexpectedShutdown' -Status 'WARN' -Detail "$($dirty.Count) unexpected shutdown / kernel-power event(s) in window" -Recommendation 'Check PSU/battery, update storage+chipset drivers, review C:\Windows\Minidump and the reliability.records section of this JSON.'
            }
        } catch { Add-Check -Area 'EventLog' -Name "Errors-$log" -Status 'SKIP' -Detail $_.Exception.Message }
    }
    $topProc = @()
    try {
        $ivSec = 2
        $cores = [Environment]::ProcessorCount
        $sample1 = @{}
        foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) { try { $sample1[$p.Id] = $p.TotalProcessorTime } catch { } }
        Start-Sleep -Seconds $ivSec
        $rows = New-Object System.Collections.ArrayList
        foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {
            if (-not $sample1.ContainsKey($p.Id)) { continue }
            try {
                $dCpu = ($p.TotalProcessorTime - $sample1[$p.Id]).TotalSeconds
                if ($dCpu -lt 0) { $dCpu = 0 }
                $null = $rows.Add([pscustomobject]@{ name = $p.ProcessName; memMB = [Math]::Round($p.WorkingSet64 / 1MB); cpuPct = [Math]::Round($dCpu / ($ivSec * $cores) * 100, 1) })
            } catch { }
        }
        $topProc = @($rows | Sort-Object memMB -Descending | Select-Object -First 5 | ForEach-Object { "$($_.name)=$($_.memMB)MB,cpu=$($_.cpuPct)%" })
    } catch { }
    $rel = [ordered]@{ available = $false; source = 'Win32_ReliabilityRecords'; correlationWindowSeconds = $CorrelationSeconds; recordCount = 0; summary = $null; timelineDays = 0; timeline = @(); records = @(); note = '' }
    try {
        $failures = @(Get-CimInstance -ClassName Win32_ReliabilityRecords -ErrorAction Stop | Sort-Object TimeGenerated -Descending | Select-Object -First $ReliabilityCount)
        $rel.available = $true
        $rel.recordCount = $failures.Count
        $rel.note = "records = latest $ReliabilityCount reliability events; correlatedEvents = Critical/Error/Warning from Application+System logs within +/-$CorrelationSeconds s, sorted by severity then time proximity, capped at $MaxEventsPerRecord per record; messages truncated to $MessageMaxChars chars"
        $relRecords = New-Object System.Collections.ArrayList
        foreach ($f in $failures) {
            $t = $f.TimeGenerated
            $corr = @()
            $corrTotal = 0
            try {
                $matched = @(Get-WinEvent -FilterHashtable @{ LogName = 'Application', 'System'; Level = 1, 2, 3; StartTime = $t.AddSeconds(-$CorrelationSeconds); EndTime = $t.AddSeconds($CorrelationSeconds) } -ErrorAction SilentlyContinue)
                $corrTotal = $matched.Count
                $corr = @($matched | Sort-Object @{ Expression = { $_.Level } }, @{ Expression = { [Math]::Abs(($_.TimeCreated - $t).TotalSeconds) } } | Select-Object -First $MaxEventsPerRecord | ForEach-Object { [ordered]@{ time = (FmtTime $_.TimeCreated); log = $_.LogName; provider = $_.ProviderName; id = $_.Id; level = "$($_.LevelDisplayName)"; message = (Trunc $_.Message $MessageMaxChars) } })
            } catch { }
            $null = $relRecords.Add([ordered]@{ time = (FmtTime $t); source = '' + $f.SourceName; product = '' + $f.ProductName; eventId = $f.EventIdentifier; message = (Trunc $f.Message $MessageMaxChars); correlatedEventCount = $corrTotal; correlatedEvents = $corr })
        }
        $rel.records = @($relRecords)
        $now = Get-Date
        $last24 = @($failures | Where-Object { $_.TimeGenerated -gt $now.AddHours(-24) }).Count
        $last7d = @($failures | Where-Object { $_.TimeGenerated -gt $now.AddDays(-7) }).Count
        $byProduct = @($failures | Group-Object { if ($_.ProductName) { $_.ProductName } else { $_.SourceName } } | Sort-Object Count -Descending)
        $rel.summary = [ordered]@{ failuresLast24h = $last24; failuresLast7d = $last7d; lastFailure = $(if ($failures.Count) { (FmtTime $failures[0].TimeGenerated) } else { $null }); topProducts = @($byProduct | Select-Object -First 5 | ForEach-Object { "$($_.Name) x$($_.Count)" }) }
        $days = [Math]::Max(1, [int][Math]::Ceiling($EventHours / 24))
        $rel.timelineDays = $days
        $today = (Get-Date).Date
        $buckets = New-Object System.Collections.ArrayList
        for ($i = $days - 1; $i -ge 0; $i--) {
            $d = $today.AddDays(-$i)
            $dayRecs = @($failures | Where-Object { $_.TimeGenerated.Date -eq $d })
            $infos = @($dayRecs | Where-Object { $_.SourceName -match 'MsiInstaller' -and $_.Message -match 'status:\s*0' })
            $fails = @($dayRecs | Where-Object { -not ($_.SourceName -match 'MsiInstaller' -and $_.Message -match 'status:\s*0') })
            $null = $buckets.Add([ordered]@{ date = $d.ToString('yyyy-MM-dd'); failures = $fails.Count; informational = $infos.Count; products = @($dayRecs | Group-Object { if ($_.ProductName) { $_.ProductName } else { $_.SourceName } } | ForEach-Object { "$($_.Name) x$($_.Count)" }) })
        }
        $rel.timeline = @($buckets)
        $rel.note += "; timeline = daily failure/informational buckets for the last $days day(s) (window follows -EventHours)"
        $st = if ($last7d -gt 5) { 'WARN' } elseif ($last7d -gt 0) { 'INFO' } else { 'PASS' }
        Add-Check -Area 'Reliability' -Name 'RecentFailures' -Status $st -Detail "$($failures.Count) reliability record(s) collected; last 24h: $last24; last 7d: $last7d; top: $(($rel.summary.topProducts -join '; '))" -Recommendation $(if ($st -eq 'WARN') { 'Frequent app/Windows failures: analyze reliability.records[].correlatedEvents for faulting modules; update/reinstall affected apps and drivers.' } else { '' })
        $repeat = @($byProduct | Where-Object { $_.Count -ge 3 })
        if ($repeat.Count) {
            Add-Check -Area 'Reliability' -Name 'RecurringFailures' -Status 'WARN' -Detail ('Repeated failures (>=3 in window): ' + (($repeat | ForEach-Object { "$($_.Name) x$($_.Count)" }) -join '; ')) -Recommendation 'Recurring crash source: inspect its reliability.records entries + correlatedEvents (faulting module / exception code), then patch, reinstall, or roll back that component.'
        } else {
            Add-Check -Area 'Reliability' -Name 'RecurringFailures' -Status 'PASS' -Detail 'No product failed 3+ times in the collected window'
        }
    } catch {
        $rel.note = 'Win32_ReliabilityRecords unavailable: ' + $_.Exception.Message
        Add-Check -Area 'Reliability' -Name 'RecentFailures' -Status 'SKIP' -Detail 'Reliability records not readable (RACAgent disabled or WMI repository issue)' -Recommendation 'Verify scheduled task \Microsoft\Windows\RAC\RACAgent is enabled; view locally with perfmon /rel.'
    }
    if (-not $NoReliabilityMonitor) {
        try {
            Start-Process -FilePath "$env:windir\System32\perfmon.exe" -ArgumentList '/rel' -ErrorAction Stop
            $out.relMonitorLaunched = $true
        } catch { $out.relMonitorError = $_.Exception.Message }
    }
    $nFail  = @($script:Checks | Where-Object { $_['status'] -eq 'FAIL' }).Count
    $nWarn  = @($script:Checks | Where-Object { $_['status'] -eq 'WARN' }).Count
    $nPass  = @($script:Checks | Where-Object { $_['status'] -eq 'PASS' }).Count
    $nInfo  = @($script:Checks | Where-Object { $_['status'] -eq 'INFO' }).Count
    $nSkip  = @($script:Checks | Where-Object { $_['status'] -eq 'SKIP' }).Count
    $score  = [Math]::Max(0, [Math]::Min(100, 100 - 15 * $nFail - 5 * $nWarn))
    $overall = if ($nFail) { 'FAIL' } elseif ($nWarn) { 'WARN' } else { 'PASS' }
    $out.status  = 'ok'
    $out.overall = $overall
    $out.score   = $score
    $out.counts  = [ordered]@{ pass = $nPass; warn = $nWarn; fail = $nFail; info = $nInfo; skip = $nSkip }
    $out.inventory = [ordered]@{ computer = $invComputer; user = $invUser; hardware = $invHardware; runtime = [ordered]@{ topProcesses = $topProc; volumes = $volsTxt } }
    $out.checks      = @($script:Checks)
    $out.reliability = $rel
    $out.remediation = @($script:Checks | Where-Object { $_['recommendation'] } | ForEach-Object { '[{0}/{1}] {2}' -f $_['area'], $_['name'], $_['recommendation'] })
    if ($ReportPath) {
        try {
            if (-not [System.IO.Path]::IsPathRooted($ReportPath)) { $ReportPath = Join-Path (Get-Location).Path $ReportPath }
            $dir = Split-Path $ReportPath -Parent
            if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
            Write-HtmlReport -Path $ReportPath
            $out.reportFile = $ReportPath
        } catch { $out.reportError = $_.Exception.Message }
    }
    Emit-Result -Message ("Self-check completed: overall=$overall score=$score ($nFail fail / $nWarn warn / $nPass pass / $nSkip skipped); reliability records=$($rel.recordCount)")
}
catch {
    Emit-Result -Code 1 -Message ('FAILED: ' + $_.Exception.Message)
}
