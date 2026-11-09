Add-Type -AssemblyName System.Drawing

function Describe-Image($path) {
    if (Test-Path $path) {
        $img = [System.Drawing.Bitmap]::FromFile($path)
        Write-Output "$path : $($img.Width)x$($img.Height) format=$($img.PixelFormat)"
        # Check non-transparent bounding box
        $minX = $img.Width; $minY = $img.Height; $maxX = 0; $maxY = 0
        $nonAlpha = 0
        for ($y = 0; $y -lt $img.Height; $y += 4) {
            for ($x = 0; $x -lt $img.Width; $x += 4) {
                $c = $img.GetPixel($x, $y)
                if ($c.A -gt 20) {
                    $nonAlpha++
                    if ($x -lt $minX) { $minX = $x }
                    if ($x -gt $maxX) { $maxX = $x }
                    if ($y -lt $minY) { $minY = $y }
                    if ($y -gt $maxY) { $maxY = $y }
                }
            }
        }
        Write-Output "  Non-alpha count: $nonAlpha, Box: ($minX, $minY) - ($maxX, $maxY)"
        $img.Dispose()
    } else {
        Write-Output "Not found: $path"
    }
}

Describe-Image "C:\DieHardROS\Documents\res\txt_logo_zjzc.png"
Describe-Image "C:\DieHardROS\Documents\res\dh_brand\dh_bg1.jpg"
Describe-Image "C:\DieHardROS\Documents\res\dh_brand\dh_rank_s1.jpg"

