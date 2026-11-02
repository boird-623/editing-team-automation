@echo off
REM upscale.bat
REM 用途：技能B「素材修复与溯源」在没有云端画质增强（火山引擎）可用时，
REM       调用本脚本做本地超分辨率处理。
REM
REM 用法：
REM     upscale.bat 输入文件.mp4 输出文件.mp4 倍数(2或4)
REM
REM 依赖（需提前手动安装，脚本不负责自动下载安装）：
REM     - Real-ESRGAN-ncnn-vulkan 可执行文件，需放在本脚本同目录下，
REM       或者把它所在目录加入系统 PATH，可执行文件名需为 realesrgan-ncnn-vulkan.exe
REM       下载地址（需人工下载，不要让脚本自动联网下载）：
REM       https://github.com/xinntao/Real-ESRGAN/releases
REM     - ffmpeg 已加入系统 PATH（用于拆帧和重新编码）
REM
REM 说明：
REM     本脚本先用 ffmpeg 把视频拆成帧图片，逐帧跑 Real-ESRGAN 超分，
REM     再用 ffmpeg 把超分后的帧重新编码为视频，并保留原音轨。
REM     处理较慢，显卡性能和视频时长直接决定耗时，
REM     技能B会按约束只对关键片段（3-10秒）调用本脚本，不建议整条长视频跑。

setlocal enabledelayedexpansion

if "%~1"=="" (
    echo [错误] 用法: upscale.bat 输入文件 输出文件 倍数
    exit /b 1
)
if "%~2"=="" (
    echo [错误] 用法: upscale.bat 输入文件 输出文件 倍数
    exit /b 1
)

set INPUT=%~1
set OUTPUT=%~2
set SCALE=%~3
if "%SCALE%"=="" set SCALE=2

if not exist "%INPUT%" (
    echo [错误] 找不到输入文件: %INPUT%
    exit /b 1
)

where realesrgan-ncnn-vulkan.exe >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 realesrgan-ncnn-vulkan.exe，请先手动下载并加入 PATH 或放在本脚本同目录。
    echo 下载地址: https://github.com/xinntao/Real-ESRGAN/releases
    exit /b 1
)

where ffmpeg.exe >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 ffmpeg，请先手动安装并加入系统 PATH。
    exit /b 1
)

set TMPDIR=%TEMP%\upscale_%RANDOM%
mkdir "%TMPDIR%"
mkdir "%TMPDIR%\in"
mkdir "%TMPDIR%\out"

echo [1/4] 拆帧...
ffmpeg -y -i "%INPUT%" "%TMPDIR%\in\frame_%%06d.png"
if errorlevel 1 (
    echo [错误] 拆帧失败
    goto :cleanup_fail
)

echo [2/4] 超分处理 (倍数 x%SCALE%)...
realesrgan-ncnn-vulkan.exe -i "%TMPDIR%\in" -o "%TMPDIR%\out" -s %SCALE%
if errorlevel 1 (
    echo [错误] 超分处理失败，可能是显卡不兼容或显存不足
    goto :cleanup_fail
)

echo [3/4] 提取原音轨...
ffmpeg -y -i "%INPUT%" -vn -acodec copy "%TMPDIR%\audio.aac" 2>nul

echo [4/4] 重新编码为视频...
if exist "%TMPDIR%\audio.aac" (
    ffmpeg -y -framerate 30 -i "%TMPDIR%\out\frame_%%06d.png" -i "%TMPDIR%\audio.aac" -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "%OUTPUT%"
) else (
    ffmpeg -y -framerate 30 -i "%TMPDIR%\out\frame_%%06d.png" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%"
)

if errorlevel 1 (
    echo [错误] 重新编码失败
    goto :cleanup_fail
)

echo 完成，输出文件: %OUTPUT%
rmdir /s /q "%TMPDIR%"
exit /b 0

:cleanup_fail
echo [失败] 处理未完成，临时文件保留在 %TMPDIR% 供排查。
exit /b 1
