Add-Type -AssemblyName System.Drawing

$brain = "C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a"
$files = @(
    "ros_redemption_title_logo_1794018691342.jpg",
    "ros_redemption_tactical_sniper_clean_1794047799428.jpg",
    "ros_redemption_login_clean_1794046745388.jpg"
)

foreach ($f in $files) {
    $p = Join-Path $brain $f
    if (Test-Path $p) {
        $img = [System.Drawing.Image]::FromFile($p)
        Write-Output "$f : $($img.Width)x$($img.Height)"
        $img.Dispose()
    } else {
        Write-Output "Missing: $p"
    }
}

