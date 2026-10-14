# 第三方源码

应用源码与安装包在同一个 GitHub Release 发布。第三方二进制和模型未作修改，来源如下；版本及模型文件摘要也随安装包保留。

| 组件 | 源码 / 构建来源 |
|---|---|
| FFmpeg / FFprobe 9.0.2 | [对应源码](https://github.com/FFmpeg/FFmpeg/tree/946fcce07b)、[源码归档](https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz)、[Gyan 构建配置与依赖清单](https://www.gyan.dev/ffmpeg/builds/) |
| CPython 3.12.10 音频运行环境 | [源码](https://github.com/python/cpython/tree/v3.12.10) |
| CPython 3.12.14 桌面构建运行环境 | [源码](https://github.com/python/cpython/tree/v3.12.14) |
| pywebview 6.2.1 | [源码](https://github.com/r0x0r/pywebview/tree/6.2.1) |
| Transformers 4.57.1 | [源码](https://github.com/huggingface/transformers/tree/v4.57.1) |
| ONNX Runtime DirectML 1.23.0 | [源码](https://github.com/microsoft/onnxruntime/tree/v1.23.0) |
| CLAP 原模型 | [模型与说明](https://huggingface.co/laion/clap-htsat-unfused) |
| CLAP ONNX 导出 | [固定模型版本](https://huggingface.co/Xenova/clap-htsat-unfused/tree/c28f2883575e590e04d3146ff0713c2448d691ba) |

其他 Python 依赖版本见 `requirements-audio-lock.txt`，其源码主页、版权及许可在安装目录的 `.dist-info/METADATA` 与许可证文件中保留。

FFmpeg 编译参数可用 `_internal/bin/ffmpeg.exe -buildconf` 获取。GPL 全文随应用分发；Gyan 构建页面提供链接库信息和第三方构建来源。
