# Open the report in Word (hidden), update the table of contents, the lists of figures/tables, caption numbers
# and page numbers, save it, and export a PDF next to it.
#   powershell -ExecutionPolicy Bypass -File report\finalize_report.ps1
param([string]$Docx = (Join-Path $PSScriptRoot "Hot_Oceans_Report_253318_v2.docx"))
$Docx = (Resolve-Path $Docx).Path
$Pdf = [IO.Path]::ChangeExtension($Docx, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($Docx, $false, $false, $false)
    for ($pass = 1; $pass -le 2; $pass++) {          # twice: page numbers settle after the lists grow
        $null = $doc.Fields.Update()
        foreach ($t in $doc.TablesOfContents) { $null = $t.Update() }
        foreach ($t in $doc.TablesOfFigures) { $null = $t.Update() }
        $doc.Repaginate()
    }
    $doc.Save()
    "saved: $Docx"
    $doc.ExportAsFixedFormat($Pdf, 17)               # 17 = wdExportFormatPDF; Word may drop the COM link after this
    "pdf:   $Pdf"
    try { $doc.Close($false) } catch { }
}
finally {
    $word.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
