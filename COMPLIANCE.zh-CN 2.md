# 许可证合规说明

说明这个补丁为什么可以分发，以及各项许可证对它的要求。

简要的说：**补丁里不含任何 PdfCraft 代码，编译在用户自己的机器上完成，组装出的应用
附带所有适用的许可证、声明与署名。**

[English](COMPLIANCE.md)

## 补丁本身分发的是什么

脚本里既没有 PdfCraft 的源代码，也没有它的二进制。它在用户自己的机器上：

1. 从 GitHub 检出 PdfCraft 源码（固定到验证过的提交）
2. 应用 `pdfcraft-zh.patch`（这是一个 diff，不是源文件）
3. 在本地编译

补丁仓库除了下面[第三方资源](#第三方资源)里列出的文件之外，不转发任何东西。

## 各项要求与履行方式

| 组件 | 许可证 | 要求 | 履行情况 |
|---|---|---|---|
| PdfCraft 源码 | MIT OR Apache-2.0 | 保留版权与许可证。Apache-2.0 还要求带 NOTICE，并要求**修改过的文件带醒目声明** | 两份许可证文本与 NOTICE 都随应用分发。8 个改过的文件各带一行 `Modified by pdfcraft-zh` 头部注释。`licenses/DERIVATION.txt` 列出全部改动 |
| PP-OCRv5 识别模型 | Apache-2.0 | 保留版权与许可证 | 原样再分发。署名在 `models/ATTRIBUTION.txt`，许可证文本随应用分发。上游没有 NOTICE 文件，因此 Apache-2.0 §4(d) 不适用 |
| ocrs 文字检测模型 | CC-BY-SA-4.0 | 署名、给出许可证链接、注明是否修改 | 署名与链接在 `models/ATTRIBUTION.txt`，许可证全文随应用分发。**未做任何修改**地再分发 |
| Noto Sans CJK SC 字体 | OFL-1.1 | 保留版权声明与许可证；不得使用保留字体名（Reserved Font Name） | 许可证随应用分发。**字体未修改**，也未使用任何保留名 |
| ocrs-cjk 引擎 | MIT OR Apache-2.0 | 保留版权与许可证 | 作为 Cargo 依赖编译进去。它的许可证与 PdfCraft 相同（MIT / Apache-2.0），已由随包的两份文本覆盖 |
| PdfCraft 应用图标 | MIT OR Apache-2.0 | 保留版权与许可证；标注修改 | `licenses/ICON.txt` 说明来源，并注明所做的唯一修改（每个尺寸上叠加了一个中文角标） |

## 几个值得关注的点

### 商标

「PdfCraft」「ArtCraft」这两个名称、字标和 logo 是 ArtCraft Team 的商标，**不在开源
许可证的覆盖范围内**。上游的 `NOTICE` 明确写了这一点，Apache-2.0 §6 也明确不授予任何
商标许可。

因此本补丁：

- **不修改**界面里任何 ArtCraft 品牌元素 —— ArtCraft 社区横幅、Discord 链接、官网链接、
  隐私声明全部原样保留，与上游发布的一模一样；
- 把组装出的应用命名为 `PdfCraft-zh`，并使用独立的 Bundle ID
  （`ai.storyteller.pdfcraft.zh`），使它不会被误认为官方发布；
- 在 `licenses/DERIVATION.txt` 中声明这是非官方构建，未由 ArtCraft Team 制作、背书或支持。

### 界面字体不随补丁分发

苹方、微软雅黑、文泉驿都是运行时从用户自己的操作系统里读取的。没有任何系统字体被打包
或再分发。

### CC-BY-SA-4.0 的 ShareAlike 不会传染

检测模型是逐字节原样再分发的。它与 MIT 许可的代码构成**聚合**，
而不是衍生作品，因此不要求整个应用改用 CC-BY-SA 许可。

## 安装后的应用里，许可证放在哪

| 平台 | 目录 |
|---|---|
| macOS | `PdfCraft-zh.app/Contents/Resources/licenses/` |
| Windows | `pdfcraft.exe` 同级的 `licenses\` |
| Linux | `~/.local/share/pdfcraft/licenses/` |

模型署名放在模型旁边，即 `models/ATTRIBUTION.txt`（macOS 在
`Contents/Resources/models/`，Windows 在 `models\`，Linux 在
`~/.local/share/pdfcraft/models/`）。

## 第三方资源

| 资源 | 来源 | 许可证 |
|---|---|---|
| PP-OCRv5 识别模型 | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0 |
| ocrs 文字检测模型 | [ocrs-models](https://github.com/robertknight/ocrs-models) | CC-BY-SA-4.0 |
| Noto Sans CJK SC 字体 | [craft-fonts](https://github.com/storytold/craft-fonts) / [Noto CJK](https://github.com/notofonts/noto-cjk) | OFL-1.1 |
| ocrs-cjk 引擎 | [kent-tokyo/ocrs-cjk](https://github.com/kent-tokyo/ocrs-cjk) | MIT / Apache-2.0 |
| PdfCraft 应用图标 | [storytold/pdfcraft](https://github.com/storytold/pdfcraft) | MIT OR Apache-2.0 |

---

*本文档说明本项目的许可证处理思路，不构成法律意见。*
