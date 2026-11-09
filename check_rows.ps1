Add-Type -AssemblyName System.Drawing

$bmp = [System.Drawing.Bitmap]::FromFile('C:\DieHardROS\Documents\res\dh_brand\dh_bg1.jpg')
for ($y = 0; $y -lt 120; $y += 10) {
    $c = $bmp.GetPixel(688, $y)
    Write-Output "Y=$($y) : R=$($c.R), G=$($c.G), B=$($c.B)"
}
$bmp.Dispose()
