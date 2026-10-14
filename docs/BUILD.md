# 构建与验证

需要 Windows x64、Python 3.12 和 .NET SDK 8 或更新版本。安装包不要求用户另装 Python 或 .NET SDK。

```powershell
python -m pip install -r requirements-dev.txt
./setup-audio.ps1 -Python python
./build-msi.ps1 -Python python
```

输出为 `releases/workstudio-1.0.0-x64.msi`。WiX 5.0.2 安装到项目的 `.build-deps/wix`，不修改系统 PATH。程序先构建到 `dist-release/workstudio`，再加入可迁移的 Python embedded 3.12.10、音频依赖和已校验的 CLAP 模型。

FFmpeg/FFprobe 9.0.2 从固定构建地址下载，并检查 SHA-256。模型固定到 `c28f2883575e590e04d3146ff0713c2448d691ba`；每个文件摘要保存在 `models/clap/manifest.json`。安装包内的 `BUILD-INFO.json` 记录运行环境和模型来源。

```powershell
python download_media_tools.py
python -m unittest discover -v
python installer/verify_payload.py dist-release/workstudio
```

单元测试使用临时生成的素材；离线推理检查使用生成的正弦波，不依赖作者的媒体硬盘。

GitHub Actions 的 Check 自动运行单元测试；Build MSI 可手动触发，下载构建产物后自行发布 Release。

## 安装行为

- 每用户安装，默认 `%LOCALAPPDATA%\Programs\workstudio`，可选择路径。
- 创建开始菜单和桌面快捷方式，注册 Windows 应用卸载项。
- 固定 UpgradeCode，后续版本可执行大版本升级；拒绝降级。
- 首次运行为空素材库，不会扫描作者或用户的预设磁盘。
- 索引、收藏、缓存保留在 `%LOCALAPPDATA%\AEStudio`，升级和卸载不会删除这些数据或原始素材。
- 界面需要 Microsoft Edge WebView2 Runtime。Windows 11 通常已包含；缺失时从微软官网安装。
- 当前公开包未购买代码签名证书，发布页提供 SHA-256 供核对。

## 发布

更新 `VERSION` 和 `CHANGELOG.md`，构建并在测试目录验证安装、修复和卸载。确认安装清单不含个人资料，再发布对应 Git 标签、MSI、SHA256SUMS 和第三方源码说明。
