<p align="center"><img src="public/icon.svg" width="96" alt="workstudio"></p>
<h1 align="center">workstudio</h1>
<p align="center">一个窗口，整理你的影音素材。</p>

workstudio 是 Windows 本地素材管理器，统一浏览 **AE 模板、视频、音频和图片**。素材保留原位置，支持多个硬盘和文件夹。

[下载 Windows MSI](https://github.com/XXLDinosaur/workstudio/releases/latest) · [构建说明](docs/BUILD.md) · [更新记录](CHANGELOG.md) · [GPL-3.0](LICENSE)

## 安装

从 Releases 下载 `workstudio-1.0.0-x64.msi`，双击安装。支持 Windows 10/11 x64，默认安装到当前用户目录。安装包内置 FFmpeg、FFprobe、Python 运行环境和 CLAP 声音模型，无需手动配置 Python 或另装编解码器。

界面需要 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。Windows 11 通常已包含；缺失时先安装该运行库。当前安装包没有代码签名，发布页同时提供 SHA-256 校验文件。

启动后点击左下角「管理素材库」，添加你的磁盘或文件夹。软件不会附带任何模板、视频、图片或音乐素材。

## 功能

- **统一浏览**：多素材库、跨类型搜索、滚动自动加载、网格/列表、深浅主题。
- **AE 模板**：浏览模板附带的成品预览，选择工程版本并在 After Effects 中打开；不自动渲染 AEP 文件。
- **视频**：悬停预览、详情播放；不兼容浏览器的视频自动生成 H.264/AAC 预览并缓存，最高 720p，保留原文件。
- **音频**：卡片显示时长和波形，点击试听；支持连续浏览、播放器进度和音量控制。
- **智能分类**：根据中英文文件名与目录分类，并通过本地 CLAP 模型分析待分类音频。低置信度结果保留待确认，可手动修正。
- **文件信息**：容器格式、音视频编码、码率、分辨率、帧率、总帧数、时长及采样率；推算值标注「约」。
- **素材整理**：收藏、最近浏览、跨类型项目集合，定位文件、复制文件、用默认软件打开。
- **离线工作**：浏览、预览和声音分析均在本机运行，不上传素材。

声音内容分类在「管理素材库 → 音频自动整理」启动，可暂停和继续。关闭窗口后分析继续，重启电脑后可继续未完成的任务。识别结果是建议，模型相似度不等于准确率。

## 数据与兼容性

索引、收藏、设置及预览缓存保存在 `%LOCALAPPDATA%\AEStudio`；该目录名为旧版兼容而保留。移除素材库或卸载程序都不会删除原始素材。离线磁盘保留已缓存索引。

支持常见视频、音频与图片格式；损坏、加密或不被解码组件支持的文件可能无法预览。压缩包需要先解压。透明视频生成浏览用兼容预览时可能不保留透明通道，原文件不受影响。

## 开发

```powershell
python -m pip install -r requirements-dev.txt
python download_media_tools.py
python desktop.py
```

可选安装声音识别开发环境：`./setup-audio.ps1`。完整 MSI 构建和检查参见 [docs/BUILD.md](docs/BUILD.md)。Python 单元测试使用 `python -m unittest discover -v`。

## 开源许可

workstudio 使用 **GNU GPL v3**。SurfaceStudio 提供界面基础样式和 Windows 单实例/窗口交互代码，其 GPL 许可随本项目保留。第三方运行库及模型分别遵循各自许可证，见 [THIRD_PARTY.txt](THIRD_PARTY.txt)；安装目录 `licenses` 及 Python 包的 `.dist-info` 保留许可文本。

本仓库不包含任何用户素材、素材索引、收藏、模型权重或个人配置。模型与构建依赖在构建时从公开来源获取，成品安装包包含离线运行所需文件。
