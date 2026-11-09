Add-Type -AssemblyName System.Drawing

$p = "C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_login_clean_1794046745388.jpg"
$bmp = [System.Drawing.Bitmap]::FromFile($p)

Write-Output "Image size: $($bmp.Width) x $($bmp.Height)"
$topY = 9999
for ($y = 0; $y -lt 300; $y++) {
    for ($x = 200; $x -lt 1176; $x += 2) {
        $c = $bmp.GetPixel($x, $y)
        if (($c.R -gt 150 -and $c.G -gt 140 -and $c.B -gt 140) -or ($c.R -gt 160 -and $c.G -lt 50 -and $c.B -lt 50)) {
            if ($y -lt $topY) {
                $topY = $y
                Write-Output "Found wing edge at X=$($x), Y=$($y): R=$($c.R), G=$($c.G), B=$($c.B)"
                break
            }
        }
    }
    if ($topY -ne 9999) { break }
}

Write-Output "Topmost logo feature detected at Y=$($topY)"
$bmp.Dispose()
