param([Parameter(Mandatory=$true)][long]$WindowHandle, [switch]$Diagnostics, [switch]$IncludeChat, [switch]$Watch, [long]$IgnoreProcessId = 0)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
function Test-PulseComposerWrapper($parentBounds,$bounds,$windowRect,$maxHeight) {
    # The Edit reports scrollable text extent; its height may exceed the visible
    # shell. The shell includes the bottom controls, independent of text length.
    return ($parentBounds.Width -ge $bounds.Width -and $parentBounds.Width -le $bounds.Width+150 -and
        $parentBounds.Height -ge 60 -and $parentBounds.Height -le $maxHeight -and
        $parentBounds.Bottom -ge $bounds.Bottom+25 -and
        $parentBounds.Top -ge ($windowRect.Top+$windowRect.Height*0.5) -and $parentBounds.Bottom -le $windowRect.Bottom)
}
function Get-PulseContext {
    $rootElement = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle)
    $windowRect = $rootElement.Current.BoundingRectangle
    if ($windowRect.IsEmpty -or $windowRect.Width -le 0 -or $windowRect.Height -le 0) {
        # A minimized/rebuilding provider can temporarily expose an empty rectangle.
        # Unknown context must not be reported as "popup closed".
        if ($IncludeChat) { [pscustomobject]@{composer=$null; chat_title=$null; chat_status='unavailable'; interaction_open=$null} | ConvertTo-Json -Compress }
        elseif ($Diagnostics) { [pscustomobject]@{edit_count=0; candidates=@(); named_matches=0; ancestors=@()} | ConvertTo-Json -Compress }
        else { 'null' }
        return
    }
    $chatTitle = $null
    $chatStatus = 'unavailable'
    if ($IncludeChat) {
        # The main browser document's accessible Name is document.title. Read only
        # this navigation label; nested browser panels and message text are excluded.
        $documentCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
        $documents = $rootElement.FindAll([System.Windows.Automation.TreeScope]::Descendants, $documentCondition)
        $candidates = @()
        foreach ($document in $documents) {
            try {
                if ($document.Current.IsOffscreen -or $document.Current.AutomationId -ne 'RootWebArea') { continue }
                $ancestor = $document
                $depth = 0
                for ($i=0; $i -lt 24; $i++) {
                    $ancestor = [System.Windows.Automation.TreeWalker]::RawViewWalker.GetParent($ancestor)
                    $depth++
                    if ($null -eq $ancestor) { break }
                    if ([System.Windows.Automation.Automation]::Compare($ancestor,$rootElement)) {
                        $candidates += [pscustomobject]@{element=$document; depth=$depth}
                        break
                    }
                }
            } catch { continue }
        }
        if ($candidates.Count -gt 0) {
            $minimumDepth = ($candidates | Measure-Object -Property depth -Minimum).Minimum
            $mainDocuments = @($candidates | Where-Object {$_.depth -eq $minimumDepth})
            if ($mainDocuments.Count -eq 1) {
                $name = $mainDocuments[0].element.Current.Name
                if ($name.Length -gt 0 -and $name.Length -le 160 -and $name -notmatch '[\r\n]') {
                    $chatTitle = $name
                    $chatStatus = 'ok'
                }
            }
        }
    }
    $maxHeight = [Math]::Max(260, [Math]::Min(520,$windowRect.Height*0.6))
    $condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
    $elements = $rootElement.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
    $composerMatches = @()
    $composerScanReliable = $true
    $candidates = @()
    $ancestorRects = @()
    foreach ($element in $elements) {
        try {
            $bounds = $element.Current.BoundingRectangle
            if ($element.Current.IsOffscreen -or $bounds.IsEmpty) { continue }
            # Use only an accessible label; never inspect draft values or text.
            $isComposer = $element.Current.Name -match '(?i)(发送消息|创建任务|发消息|Message Codex|Send a message|Ask Codex|Message ChatGPT|Ask anything|^使用 ChatGPT Work$)'
            if ($bounds.Width -lt 180 -or $bounds.Height -lt 15 -or $bounds.Bottom -gt $windowRect.Bottom) { continue }
            $editVisible = $bounds.Height -le $maxHeight -and $bounds.Top -ge ($windowRect.Top+$windowRect.Height*0.5)
            if (-not $isComposer -and -not $editVisible) { continue }
            $candidate = if ($editVisible) { [pscustomobject]@{ left=[int]$bounds.Left; top=[int]$bounds.Top; right=[int]$bounds.Right; bottom=[int]$bounds.Bottom } } else { $null }
            $parent = $element
            $wrapper = $null
            for ($depth=0; $depth -lt 8; $depth++) {
                $parent = [System.Windows.Automation.TreeWalker]::RawViewWalker.GetParent($parent)
                if ($null -eq $parent) { break }
                $parentBounds = $parent.Current.BoundingRectangle
                if ($parentBounds.IsEmpty) { continue }
                $ancestorRects += [pscustomobject]@{ left=[int]$parentBounds.Left; top=[int]$parentBounds.Top; right=[int]$parentBounds.Right; bottom=[int]$parentBounds.Bottom }
                if (Test-PulseComposerWrapper $parentBounds $bounds $windowRect $maxHeight) {
                    $wrapper = [pscustomobject]@{ left=[int]$parentBounds.Left; top=[int]$parentBounds.Top; right=[int]$parentBounds.Right; bottom=[int]$parentBounds.Bottom }
                }
            }
            if ($null -ne $wrapper) { $candidate = $wrapper }
            if ($null -eq $candidate) { continue }
            $candidates += $candidate
            if (-not $isComposer) { continue }
            $composerMatches += $candidate
        } catch { $composerScanReliable = $false; continue }
    }
    if ($Diagnostics) { [pscustomobject]@{ edit_count=$elements.Count; candidates=$candidates; named_matches=$composerMatches.Count; ancestors=$ancestorRects } | ConvertTo-Json -Compress; return }
    $composer = $null
    if ($composerMatches.Count -eq 1) { $composer = $composerMatches[0] }
    # A lone Edit near the bottom can belong to a clarification, search or dialog.
    # Only a recognized composer label may replace the last verified geometry.
    $composerSource = if ($null -ne $composer) { 'named' } else { 'unavailable' }
    if ($IncludeChat) {
        # Inspect roles, rectangles and expanded state only. Never read popup labels,
        # draft values, message bodies, slider values or selection contents.
        $interactionOpen = $false
        $ignoredOwnElements = 0
        $popupBounds = $null
        $interactionReliable = $true
        $popupConditions = @()
        foreach ($type in @([System.Windows.Automation.ControlType]::Menu,
                            [System.Windows.Automation.ControlType]::ToolTip,
                            [System.Windows.Automation.ControlType]::Window,
                            [System.Windows.Automation.ControlType]::Pane,
                            [System.Windows.Automation.ControlType]::Group,
                            [System.Windows.Automation.ControlType]::Button,
                            [System.Windows.Automation.ControlType]::ComboBox)) {
            $popupConditions += New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $type)
        }
        $popupCondition = New-Object System.Windows.Automation.OrCondition(,$popupConditions)
        try {
            $popupElements = $rootElement.FindAll([System.Windows.Automation.TreeScope]::Descendants, $popupCondition)
            foreach ($popup in $popupElements) {
                try {
                    $current = $popup.Current
                    # Our owned strip, blur host and tooltip are UIA descendants
                    # of the target too. Never treat them as a host popover.
                    if ($IgnoreProcessId -gt 0 -and $current.ProcessId -eq $IgnoreProcessId) {
                        $ignoredOwnElements++
                        continue
                    }
                    $bounds = $current.BoundingRectangle
                    if ($current.IsOffscreen -or $bounds.IsEmpty -or $bounds.Width -le 0 -or $bounds.Height -le 0) { continue }
                    $type = $current.ControlType
                    if ($type -eq [System.Windows.Automation.ControlType]::Menu -or
                        $type -eq [System.Windows.Automation.ControlType]::ToolTip -or
                        $type -eq [System.Windows.Automation.ControlType]::Window -or
                        $current.LocalizedControlType -match '(?i)^(dialog|alert dialog|dialogue|对话框|警报对话框)$') {
                        $interactionOpen = $true
                        $popupBounds = [pscustomobject]@{left=[int]$bounds.Left;top=[int]$bounds.Top;right=[int]$bounds.Right;bottom=[int]$bounds.Bottom}
                        break
                    }
                    $dialogProperty = [System.Windows.Automation.AutomationElement]::IsDialogProperty
                    if ($null -ne $dialogProperty -and $popup.GetCurrentPropertyValue($dialogProperty) -eq $true) {
                        $interactionOpen = $true
                        $popupBounds = [pscustomobject]@{left=[int]$bounds.Left;top=[int]$bounds.Top;right=[int]$bounds.Right;bottom=[int]$bounds.Bottom}
                        break
                    }
                    # Sidebar project headers can also be expanded buttons. Only
                    # composer controls count as a popover trigger.
                    if ($null -eq $composer -or $type -notin @([System.Windows.Automation.ControlType]::Button, [System.Windows.Automation.ControlType]::ComboBox)) { continue }
                    if ($bounds.Left -lt $composer.left-2 -or $bounds.Right -gt $composer.right+2 -or
                        $bounds.Top -lt $composer.top-2 -or $bounds.Bottom -gt $composer.bottom+2) { continue }
                    if ($popup.GetCurrentPropertyValue([System.Windows.Automation.AutomationElement]::IsExpandCollapsePatternAvailableProperty)) {
                        $expanded = $popup.GetCurrentPropertyValue([System.Windows.Automation.ExpandCollapsePatternIdentifiers]::ExpandCollapseStateProperty)
                        if ($expanded -eq [System.Windows.Automation.ExpandCollapseState]::Expanded -or
                            $expanded -eq [System.Windows.Automation.ExpandCollapseState]::PartiallyExpanded) {
                            $interactionOpen = $true
                            break
                        }
                    }
                } catch { $interactionReliable = $false }
            }
        } catch { $interactionReliable = $false }
        if (-not $interactionOpen -and -not $interactionReliable) { $interactionOpen = $null }
        $composerStatus = if ($null -ne $composer) { 'found' } elseif ($composerScanReliable) { 'absent' } else { 'unavailable' }
        [pscustomobject]@{composer=$composer; composer_source=$composerSource; composer_status=$composerStatus; chat_title=$chatTitle; chat_status=$chatStatus; interaction_open=$interactionOpen;popup_bounds=$popupBounds;ignored_own_elements=$ignoredOwnElements} | ConvertTo-Json -Compress -Depth 3
    } elseif ($null -ne $composer) { $composer | ConvertTo-Json -Compress }
    else { 'null' }
}

if ($Watch) {
    # The parent sends one request at a time. EOF shuts down the helper; no timer
    # runs while the app is inactive. Assemblies stay loaded between requests.
    while ($null -ne ($command = [Console]::ReadLine())) {
        if ($command -eq 'exit') { break }
        if ($command -ne 'probe') { continue }
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        try { $value = Get-PulseContext | ConvertFrom-Json }
        catch { $value = [pscustomobject]@{composer=$null; chat_title=$null; chat_status='unavailable'; interaction_open=$null} }
        $timer.Stop()
        $value | Add-Member -NotePropertyName probe_pid -NotePropertyValue $PID -Force
        $value | Add-Member -NotePropertyName probe_ms -NotePropertyValue $timer.Elapsed.TotalMilliseconds -Force
        [Console]::WriteLine(($value | ConvertTo-Json -Compress -Depth 4))
        [Console]::Out.Flush()
    }
} else { Get-PulseContext }
