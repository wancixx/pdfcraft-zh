# pdfcraft-zh

给 [PdfCraft](https://github.com/storytold/pdfcraft) 加上更好的中文体验。

一个 Python 脚本，在本地检出 PdfCraft 源码、打上补丁、编译，并把结果组装成一个独立的
应用装进你的用户目录。**不改动任何原有界面元素** —— 只是让中文显示得更合适，并让扫描件
里的中文能被识别出来。

[English documentation](README.md)

![中文 OCR：原版 PdfCraft 与 pdfcraft-zh 对比](docs/ocr-comparison.png)

## 做了什么

| 项目 | 改动 |
|---|---|
| **界面字体** | 中文改用系统自带字体：macOS 苹方、Windows 微软雅黑、Linux 文泉驿。不再因找不到字体而回退到偏细的日文字体 |
| **界面语言** | 精简为 简体中文 / 繁體中文 / 日本語 / English（其余 19 种语言目录移除） |
| **中文 OCR** | 扫描与 OCR 支持中文：用 PaddleOCR 的 PP-OCRv5 识别模型（简/繁/日/英通用），识别结果作为**可搜索的隐形文本层**写回 PDF |
| **安装方式** | 组装成独立的 `PdfCraft-zh`，与原版**并存**而不是替换它 |

前两项是本地化的取舍；第三项是官方尚未提供的功能（上游 ocrs 的 CJK 支持长期停留在规划阶段）。

## 装到哪里

| 系统 | 位置 |
|---|---|
| **macOS** | `~/Applications/PdfCraft-zh.app` |
| **Windows** | `%LOCALAPPDATA%\PdfCraft-zh\`，并在桌面创建快捷方式 |
| **Linux** | `~/.local/bin/pdfcraft` + `~/.local/share/applications/pdfcraft-zh.desktop` |

**原版 PdfCraft 不会被修改、移动或删除。** 两者使用不同的应用标识
（`ai.storyteller.pdfcraft.zh` 与 `ai.storyteller.pdfcraft`），因此可以同时安装、同时运行，在 Dock / 开始菜单里也分得开。

我们的补丁自带一个图标 —— PdfCraft 原图标右下角加了一个中文角标，便于与原版区分。

## 用法

**不需要预先安装 Python。** 启动器会用系统自带的方式找到（必要时引导你安装）Python，
然后运行主脚本。

| 系统 | 怎么开始 |
|---|---|
| **Windows** | 双击 **`run.bat`** |
| **macOS / Linux** | 终端里运行 **`./run.sh`** |

也可以直接运行主脚本（如果你已经有 Python）：

```bash
python3 pdfcraft-zh.py
```

脚本会依次：

1. 检查系统与环境（git、Rust 工具链）
2. 准备中文 OCR 模型与字体（约 100 MB，带进度与网速）
3. 应用代码补丁
4. 编译 PdfCraft
5. 自检
6. 组装并安装

完成后即可在应用程序列表里找到 **PdfCraft-zh**（Windows 上还会在桌面创建快捷方式）。

**macOS里首次打开若被系统拦截**（本地构建，没有 Apple 开发者签名），
在「系统设置 → 隐私与安全性」点「仍要打开」。这一步只需做一次。

### 选项

```bash
python3 pdfcraft-zh.py --dir DIR      # 指定工作目录（默认当前目录）
python3 pdfcraft-zh.py --jobs 8       # 指定编译并行度
python3 pdfcraft-zh.py --check        # 只做环境与资产检查，不编译
python3 pdfcraft-zh.py --no-install   # 只编译，不组装也不安装
```

### 环境要求

- **Python 3.8+** —— 用 `run.sh` / `run.bat` 启动的话会自动检测，缺失时给出安装指引。
  主脚本只用标准库，**无需 pip**。
- **git**
- **Rust 工具链**：<https://rustup.rs>
  ```bash
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  ```
- 消耗磁盘约 **3 GB**（源码 + 依赖 + 编译产物 + 模型）

## 网络问题

### 识别模型（约 80 MB，托管在 Hugging Face）

脚本默认先用国内镜像 `hf-mirror.com`，失败后自动切到 `huggingface.co`，
并按 5 MB 分段下载 + 重试（长连接容易被中断）。

**如果仍然超时或被中断**，请手动下载后放到指定目录，再重新运行脚本即可（会跳过已完成的步骤）：

```bash
curl -L -C - -o PP-OCRv5_server_rec_infer.onnx \
  https://hf-mirror.com/marsena/paddleocr-onnx-models/resolve/main/PP-OCRv5_server_rec_infer.onnx
```

放到 `pdfcraft/assets/models/` 下（脚本会自动改名为 `text-recognition.onnx`），然后重新运行。

校验值（脚本会自动核对）：

```
SHA256  13d0dda27d63dc0f4938af48df2c55b33f3c989a0bd5eacb8410e30f1735f644
大小    84505505 字节（80.6 MB）
```

### 检测模型（约 2.4 MB）

这个模型只负责找出文字的位置、不认字，因此中英文通用 —— 直接沿用官方那一份。
官方下载源在国内多数网络下连不通，所以我们的脚本按下面的顺序找：

1. 本补丁 `assets/` 目录里的副本
2. 工作目录
3. 本机已安装的 PdfCraft（macOS 在 `PdfCraft.app/Contents/Resources/models/`）
4. 联网下载

### 源码仓库

三个 GitHub 仓库（PdfCraft 源码、craft-fonts、ocrs-cjk）会依次尝试多个加速镜像。
每个镜像下先试 GitHub 的打包下载（一次 HTTP GET，支持断点续传），失败再试 `git` 浅取。
每次失败的残留都会被清干净，所以重跑一定能继续 —— 不会卡在半成品目录上。

如果所有镜像都不通，脚本会打印出可直接复制的手动下载命令。把结果放到工作目录下对应的
位置（`pdfcraft/`、`craft-fonts/`、`vendor/ocrs-cjk/`）再重新运行即可，已存在的会被复用。

## 为什么固定 upstream 版本

补丁基于 PdfCraft 的提交 `afa8e184` 验证，脚本会检出该版本，以保证补丁必定应用成功。
上游更新后，补丁可能需要同步调整。

## 自检

脚本最后会核对：编译产物存在、二进制包含中文支持特征、界面字体与语言改动生效、
OCR 资产齐全（识别模型、检测模型、字符表长度、嵌入字体）。任一项不符合会以红色标出，
并且不会继续安装。

安装完成后脚本还会验证应用包的签名，确保 `codesign --verify --strict` 通过。

## 目录内容

| 文件 | 说明 |
|---|---|
| `pdfcraft-zh.py` | 主脚本（补丁内嵌，自包含） |
| `run.sh` `run.command` `run.ps1` `run.bat` | 各平台启动器 |
| `pdfcraft-zh.patch` | 代码补丁（`git apply` 格式，8 个文件） |
| `COMPLIANCE.md` `COMPLIANCE.zh-CN.md` | 逐项说明各项许可证的要求如何履行 |
| `docs/ocr-comparison.png` | 中文扫描件上原版与 pdfcraft-zh 的对比 |
| `assets/PdfCraft-zh.icns` | 应用图标（macOS） |
| `assets/PdfCraft-zh.png` | 应用图标（Linux） |
| `assets/text-detection.rten` | 文字检测模型 |
| `assets/licenses/` | 随应用分发的许可证全文 |
| `tools/script_template.py` | 开发用模板，补丁位置留 `__CODE_PATCH__` 占位符 |
| `tools/build.py` | 由模板与补丁生成 `pdfcraft-zh.py` |

改动补丁或模板后，运行 `python3 tools/build.py` 重新生成主脚本。

## 许可证与合规

本补丁脚本以 MIT 许可证发布（`LICENSE`）。

### 补丁本身分发的是什么

脚本**不包含** PdfCraft 的源代码或二进制。它在用户自己的机器上从 GitHub 检出源码、
应用 `pdfcraft-zh.patch`、本地编译。补丁文件里只有 diff，没有 PdfCraft 的完整源文件。

### 组装出的应用里附带的许可证

安装后的应用带一整套许可证（macOS 在 `PdfCraft-zh.app/Contents/Resources/`，
Windows 在 `licenses\`，Linux 在 `~/.local/share/pdfcraft/licenses/`）：

| 文件 | 内容 |
|---|---|
| `licenses/PdfCraft-LICENSE-MIT.txt` | PdfCraft 的 MIT 许可证 |
| `licenses/PdfCraft-LICENSE-APACHE.txt` | PdfCraft 的 Apache-2.0 许可证 |
| `licenses/PdfCraft-NOTICE.txt` | PdfCraft 的 NOTICE |
| `licenses/DERIVATION.txt` | 改动清单、商标声明、未改动声明 |
| `licenses/ICON.txt` | 图标的来源与修改说明 |
| `licenses/OFL-NotoSansCJKsc.txt` | 嵌入字体的 OFL-1.1 许可证 |
| `licenses/CC-BY-SA-4.0.txt` | 检测模型的 CC-BY-SA-4.0 全文 |
| `licenses/PaddleOCR-LICENSE-APACHE.txt` | 识别模型的 Apache-2.0 许可证 |
| `licenses/PdfCraft-zh-LICENSE.txt` | 本补丁自己的 MIT |
| `models/ATTRIBUTION.txt` | 两个 OCR 模型与嵌入字体的署名 |

各项许可证要求如何履行 —— 商标、不随分发的界面字体、CC-BY-SA 的 ShareAlike 为何不传染
—— 见 [COMPLIANCE.zh-CN.md](COMPLIANCE.zh-CN.md)。

### 第三方资源一览

| 资源 | 来源 | 许可证 |
|---|---|---|
| PP-OCRv5 识别模型 | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0 |
| ocrs 文字检测模型 | [ocrs-models](https://github.com/robertknight/ocrs-models) | CC-BY-SA-4.0 |
| Noto Sans CJK SC 字体 | [craft-fonts](https://github.com/storytold/craft-fonts) / [Noto CJK](https://github.com/notofonts/noto-cjk) | OFL-1.1 |
| ocrs-cjk 引擎 | [kent-tokyo/ocrs-cjk](https://github.com/kent-tokyo/ocrs-cjk) | MIT / Apache-2.0 |
| PdfCraft 应用图标 | [storytold/pdfcraft](https://github.com/storytold/pdfcraft) | MIT OR Apache-2.0 |
