Add-Type -AssemblyName System.Drawing

$img = [System.Drawing.Image]::FromFile('C:\DieHardROS\Documents\res\dh_brand\dh_bg1.jpg')
Write-Output "dh_bg1.jpg: $($img.Width)x$($img.Height)"
$img.Dispose()

