# Convert .docx files to PDF with the installed Microsoft Word (COM automation). Read-only on the inputs.
#   powershell -NoProfile -File paper\scripts\docx2pdf.ps1 <in.docx> [<out.pdf>]
param([Parameter(Mandatory = $true)][string]$In, [string]$Out = "")
$inPath = (Resolve-Path $In).Path
if (-not $Out) { $Out = [System.IO.Path]::ChangeExtension($inPath, ".pdf") }
$outPath = [System.IO.Path]::GetFullPath($Out)
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($inPath, $false, $true)
  $doc.SaveAs([ref]$outPath, [ref]17)   # 17 = wdFormatPDF
  $doc.Close([ref]0)
  Write-Output "PDF: $outPath"
} finally {
  $word.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
