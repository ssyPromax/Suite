# 非破坏性编译校验：只验证资源与 Java 源码能编译，不打包、不覆盖 dist/。
$ErrorActionPreference = 'Stop'
$proj = 'D:\.dswork\App\ChinGlish'
$sdk = "$env:LOCALAPPDATA\Android\Sdk"
$jdk = 'C:\Program Files\Java\jdk-21.0.11'
$androidJar = "$sdk\platforms\android-37.0\android.jar"
$bt = "$sdk\build-tools\36.0.0"
$aapt2 = "$bt\aapt2.exe"

$tmp = Join-Path $env:TEMP 'chinglish-verify'
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path "$tmp\gen", "$tmp\classes" | Out-Null

"=== aapt2 compile ==="
& $aapt2 compile --dir "$proj\app\res" -o "$tmp\res.zip"
if ($LASTEXITCODE -ne 0) { throw "aapt2 compile failed" }

"=== aapt2 link ==="
& $aapt2 link -o "$tmp\raw.apk" -I $androidJar --manifest "$proj\app\AndroidManifest.xml" --java "$tmp\gen" -A "$proj\app\assets" "$tmp\res.zip"
if ($LASTEXITCODE -ne 0) { throw "aapt2 link failed" }

"=== javac ==="
$javaFiles = @(Get-ChildItem "$proj\app\src" -Recurse -Filter *.java | ForEach-Object { $_.FullName })
$javaFiles += @(Get-ChildItem "$tmp\gen" -Recurse -Filter *.java | ForEach-Object { $_.FullName })
& "$jdk\bin\javac.exe" --release 8 -encoding UTF-8 -classpath $androidJar -d "$tmp\classes" $javaFiles
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

"OK: resources + java compile clean ($($javaFiles.Count) files)"
Remove-Item $tmp -Recurse -Force