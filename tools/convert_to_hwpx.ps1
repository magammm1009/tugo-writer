# 한컴오피스(한글)로 .hwp / .docx 양식을 .hwpx로 바꿔 저장한다.
# 사용: powershell -ExecutionPolicy Bypass -File convert_to_hwpx.ps1 -Src <원본 폴더> -Dst <저장 폴더> -Log <로그 파일>
# 한글이 '파일 접근 허용' 창을 띄우면 사용자가 직접 「모두 허용」을 눌러야 진행된다.
param([string]$Src, [string]$Dst, [string]$Log)

$ErrorActionPreference = 'Stop'
"start $(Get-Date -Format s)" | Out-File -FilePath $Log -Encoding utf8
$hwp = New-Object -ComObject HWPFrame.HwpObject
try { $hwp.XHwpWindows.Item(0).Visible = $true } catch {}
$files = Get-ChildItem -LiteralPath $Src -Recurse -File | Where-Object { $_.Extension -in '.hwp', '.docx', '.doc' } |
    Where-Object { -not ($_.Extension -ne '.hwp' -and (Get-ChildItem -LiteralPath $_.DirectoryName -Filter '*.hwp*' -File)) }
$i = 0
foreach ($f in $files) {
    $i++
    $rel = $f.Directory.FullName.Substring((Resolve-Path -LiteralPath $Src).Path.Length).TrimStart('\')
    $outDir = Join-Path $Dst $rel
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $out = Join-Path $outDir ($f.BaseName + '.hwpx')
    if (Test-Path -LiteralPath $out) { "skip $i $rel\$($f.Name)" | Out-File -FilePath $Log -Append -Encoding utf8; continue }
    try {
        $ok = $hwp.Open($f.FullName, '', 'forceopen:true;suspendpassword:true')
        if (-not $ok) { throw 'Open 실패' }
        $ok2 = $hwp.SaveAs($out, 'HWPX', '')
        $hwp.Clear(1) | Out-Null
        "ok $i $rel\$($f.Name) -> $ok2" | Out-File -FilePath $Log -Append -Encoding utf8
    } catch {
        "fail $i $rel\$($f.Name) : $($_.Exception.Message)" | Out-File -FilePath $Log -Append -Encoding utf8
        try { $hwp.Clear(1) | Out-Null } catch {}
    }
}
try { $hwp.Quit() } catch {}
"done $(Get-Date -Format s)" | Out-File -FilePath $Log -Append -Encoding utf8
