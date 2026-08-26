[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Document
)

$ErrorActionPreference = "Stop"
$path = (Resolve-Path -LiteralPath $Document).Path
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $null

try {
    $doc = $word.Documents.Open($path, $false, $false)
    [void]$doc.Fields.Update()
    [void]$doc.Repaginate()
    foreach ($toc in $doc.TablesOfContents) {
        [void]$toc.Update()
        $toc.Range.ParagraphFormat.Alignment = 0
        $toc.Range.ParagraphFormat.SpaceBefore = 0
        $toc.Range.ParagraphFormat.SpaceAfter = 0
        $toc.Range.ParagraphFormat.LineSpacingRule = 0
        $toc.Range.Font.Size = 12
    }
    [void]$doc.Repaginate()
    foreach ($toc in $doc.TablesOfContents) {
        [void]$toc.UpdatePageNumbers()
    }

    # Word can reintroduce Office theme fonts and hyperlink blue while updating
    # the TOC. Make the final saved document deterministic for dissertation use.
    foreach ($style in $doc.Styles) {
        if (($style.Type -eq 1) -or ($style.Type -eq 2)) {
            try {
                $style.Font.Name = "Times New Roman"
                $style.Font.Color = 0
            }
            catch {
                # Some protected built-in styles reject direct COM formatting.
            }
        }
    }
    foreach ($storyType in 1..17) {
        try {
            $range = $doc.StoryRanges.Item($storyType)
        }
        catch {
            $range = $null
        }
        while ($null -ne $range) {
            $range.Font.Name = "Times New Roman"
            $range.Font.Color = 0
            $range = $range.NextStoryRange
        }
    }

    $tocCount = $doc.TablesOfContents.Count
    $pageCount = $doc.ComputeStatistics(2)
    $doc.Save()
    $doc.Close()
    $doc = $null
    Write-Host "Updated Word fields: TOC=$tocCount Pages=$pageCount"
}
finally {
    if ($null -ne $doc) {
        $doc.Close(0)
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc)
    }
    $word.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
