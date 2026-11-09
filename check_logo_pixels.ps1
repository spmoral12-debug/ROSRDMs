Add-Type -AssemblyName System.Drawing

$p = "C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_title_logo_1794018691342.jpg"
$bmp = [System.Drawing.Bitmap]::FromFile($p)
Write-Output "Corners of ros_redemption_title_logo:"
Write-Output " (0,0): $($bmp.GetPixel(0,0))"
Write-Output " (1375,0): $($bmp.GetPixel(1375,0))"
Write-Output " (0,767): $($bmp.GetPixel(0,767))"
Write-Output " (1375,767): $($bmp.GetPixel(1375,767))"
Write-Output " Center (688, 384): $($bmp.GetPixel(688,384))"
$bmp.Dispose()

