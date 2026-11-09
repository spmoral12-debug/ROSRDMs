Add-Type -AssemblyName System.Drawing

$srcPath = "C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_login_clean_1794046745388.jpg"
$destPath = "C:\DieHardROS\Documents\res\dh_brand\ros_redemption_winged_safe.jpg"

$src = [System.Drawing.Bitmap]::FromFile($srcPath)
$w = $src.Width
$h = $src.Height

$bmp = New-Object System.Drawing.Bitmap($w, $h, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality

# 1. Fill base with full image stretched
$g.DrawImage($src, 0, 0, $w, $h)

# 2. Dark overlay on top area so smoke blends smoothly
$topDark = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(230, 18, 14, 15))
$g.FillRectangle($topDark, 0, 0, $w, 180)
$topDark.Dispose()

# 3. Draw scaled version: 75% size, positioned with Y = 110 so wings start well below top border!
$scale = 0.76
$newW = [int]($w * $scale)
$newH = [int]($h * $scale)
$offsetX = [int](($w - $newW) / 2)
$offsetY = 90

$destRect = New-Object System.Drawing.Rectangle($offsetX, $offsetY, $newW, $newH)
$g.DrawImage($src, $destRect)

$g.Dispose()
$src.Dispose()

$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/jpeg" }
$encoderParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
$encoderParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, 98L)
$bmp.Save($destPath, $codec, $encoderParams)
$bmp.Dispose()

Write-Output "Successfully generated: $destPath"
