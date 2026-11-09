Add-Type -AssemblyName System.Drawing

$bmp = [System.Drawing.Bitmap]::FromFile('C:\DieHardROS\Documents\res\dh_brand\dh_bg1.jpg')
# check X from 200 to 1176 at Y=5, 10, 20, 30
for ($y = 0; $y -le 50; $y += 10) {
    $minX = 9999; $maxX = 0
    for ($x = 0; $x -lt 1376; $x++) {
        $c = $bmp.GetPixel($x, $y)
        # wing color is brighter metallic gray / silver: R > 120, G > 100, B > 100
        if ($c.R -gt 130 -and $c.G -gt 120 -and $c.B -gt 120) {
            if ($x -lt $minX) { $minX = $x }
            if ($x -gt $maxX) { $maxX = $x }
        }
    }
    Write-Output "Y=$($y): wing span X=$($minX) to $($maxX)"
}
$bmp.Dispose()

