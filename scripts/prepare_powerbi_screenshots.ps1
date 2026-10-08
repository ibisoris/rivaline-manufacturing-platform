param(
    [string]$SourceDirectory = "screenshots-temp",
    [string]$OutputDirectory = "docs/images/powerbi"
)
$ErrorActionPreference = "Stop"
# Lossless pixel crops only: preserve the report canvas and its own navigation.
Add-Type -AssemblyName System.Drawing
$null = New-Item -ItemType Directory -Force -Path $OutputDirectory
$crops = @{
    executive = @(0, 8, 1335, 748)
    inventory = @(0, 5, 1306, 749)
    forecasting = @(0, 3, 1305, 745)
    production = @(0, 0, 1298, 737)
}
$evidence = @()
foreach ($name in @("executive", "inventory", "forecasting", "production")) {
    $source = Join-Path $SourceDirectory "$name.png"
    $destination = Join-Path $OutputDirectory "$name.png"
    $image = [System.Drawing.Bitmap]::new((Resolve-Path -LiteralPath $source).Path)
    try {
        $box = $crops[$name]
        $rectangle = [System.Drawing.Rectangle]::new($box[0], $box[1], $box[2]-$box[0], $box[3]-$box[1])
        if ($rectangle.Right -gt $image.Width -or $rectangle.Bottom -gt $image.Height) {
            throw "Crop exceeds source bounds: $name"
        }
        $crop = $image.Clone($rectangle, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $crop.Save([IO.Path]::GetFullPath($destination), [System.Drawing.Imaging.ImageFormat]::Png)
            $check = [System.Drawing.Bitmap]::new([IO.Path]::GetFullPath($destination))
            try {
                if ($check.Width -ne $crop.Width -or $check.Height -ne $crop.Height) { throw "Size mismatch" }
                # Compare every decoded pixel, including alpha, using locked image buffers.
                $bounds = [System.Drawing.Rectangle]::new(0, 0, $crop.Width, $crop.Height)
                $buffers = @()
                foreach ($bitmap in @($crop, $check)) {
                    $locked = $bitmap.LockBits($bounds, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
                    try {
                        $bytes = New-Object byte[] ($locked.Stride * $locked.Height)
                        [Runtime.InteropServices.Marshal]::Copy($locked.Scan0, $bytes, 0, $bytes.Length)
                        $sha = [Security.Cryptography.SHA256]::Create()
                        try { $buffers += [Convert]::ToBase64String($sha.ComputeHash($bytes)) } finally { $sha.Dispose() }
                    } finally { $bitmap.UnlockBits($locked) }
                }
                if ($buffers[0] -ne $buffers[1]) { throw "Pixel mismatch: $name" }
            } finally { $check.Dispose() }
            $evidence += [pscustomobject][ordered]@{
                image = "$name.png"
                source_dimensions = @($image.Width, $image.Height)
                crop_box_left_top_right_bottom = $box
                output_dimensions = @($crop.Width, $crop.Height)
                source_sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLower()
                output_sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLower()
                source_bytes = (Get-Item -LiteralPath $source).Length
                output_bytes = (Get-Item -LiteralPath $destination).Length
                cropped_pixels_preserved = $true
            }
        } finally { $crop.Dispose() }
    } finally { $image.Dispose() }
}
$evidence | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $OutputDirectory "provenance.json")
$evidence | Format-Table image, source_bytes, output_bytes, cropped_pixels_preserved
