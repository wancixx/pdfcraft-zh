# Licence compliance

Why this patch may be redistributed, and what each licence requires of it.

The short version: the patch contains no PdfCraft code, the build happens on the
user's own machine, and the assembled application ships every licence text,
notice and attribution that applies. The details are below.

## What the patch itself distributes

The script contains neither PdfCraft's source code nor its binaries. On the
user's own machine it:

1. checks PdfCraft's source out from GitHub at a pinned commit,
2. applies `pdfcraft-zh.patch` (a diff, not source files),
3. builds locally.

Nothing is redistributed by the patch repository except the files listed under
[Third-party material](#third-party-material) below.

## Requirements and how they are met

| Component | Licence | Requirement | How it is met |
|---|---|---|---|
| PdfCraft source | MIT OR Apache-2.0 | Keep the copyright and licence. Apache-2.0 additionally requires the NOTICE, and that **modified files carry prominent notices** | Both licence texts and the NOTICE ship inside the app. All 8 modified files carry a `Modified by pdfcraft-zh` header comment. `licenses/DERIVATION.txt` lists every change |
| PP-OCRv5 recognition model | Apache-2.0 | Keep the copyright and licence | Redistributed unmodified. Attributed in `models/ATTRIBUTION.txt`; the licence text ships with the app. Upstream has no NOTICE file, so Apache-2.0 §4(d) does not apply |
| ocrs text detection model | CC-BY-SA-4.0 | Attribution, a link to the licence, and an indication of whether changes were made | Attribution and link in `models/ATTRIBUTION.txt`; the full licence text ships with the app. Redistributed **unmodified** |
| Noto Sans CJK SC font | OFL-1.1 | Keep the copyright notice and licence; do not use a Reserved Font Name | Licence ships with the app. The **font is unmodified** and no reserved name is used |
| ocrs-cjk engine | MIT OR Apache-2.0 | Keep the copyright and licence | Compiled in as a Cargo dependency. Its licence is the same MIT/Apache-2.0 pair already shipped for PdfCraft |
| PdfCraft application icon | MIT OR Apache-2.0 | Keep the copyright and licence; indicate modification | `licenses/ICON.txt` states the origin and the one change made (a CJK badge was composited onto each size) |

## Points worth noting

### Trademarks

The names "PdfCraft" and "ArtCraft", the wordmark and the logos are trademarks
of the ArtCraft Team and are *not* covered by the open-source licence. Upstream's
`NOTICE` says so explicitly, and Apache-2.0 §6 grants no trademark licence.

This patch therefore:

- **changes no** ArtCraft branding in the interface — the ArtCraft community
  panel, the Discord link, the website link and the privacy notice are all left
  exactly as upstream ships them;
- names the assembled application `PdfCraft-zh` and gives it a distinct bundle
  identifier (`ai.storyteller.pdfcraft.zh`), so it cannot be confused with an
  official release;
- states in `licenses/DERIVATION.txt` that this is an unofficial build, not
  produced, endorsed or supported by the ArtCraft Team.

### Interface fonts are not redistributed

PingFang, Microsoft YaHei and WenQuanYi are read from the user's own operating
system at runtime. No system font is packaged or redistributed.

### CC-BY-SA-4.0's ShareAlike does not propagate

The detection model is redistributed byte-for-byte unmodified. It aggregates
with the MIT-licensed code rather than forming a derivative work, so the
application as a whole is not required to adopt CC-BY-SA.

## Where the licences live in the installed application

| Platform | Directory |
|---|---|
| macOS | `PdfCraft-zh.app/Contents/Resources/licenses/` |
| Windows | `licenses\` beside `pdfcraft.exe` |
| Linux | `~/.local/share/pdfcraft/licenses/` |

Model attribution sits beside the models themselves, in `models/ATTRIBUTION.txt`
(macOS: `Contents/Resources/models/`, Windows: `models\`, Linux:
`~/.local/share/pdfcraft/models/`).

## Third-party material

| Resource | Source | Licence |
|---|---|---|
| PP-OCRv5 recognition model | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0 |
| ocrs text detection model | [ocrs-models](https://github.com/robertknight/ocrs-models) | CC-BY-SA-4.0 |
| Noto Sans CJK SC font | [craft-fonts](https://github.com/storytold/craft-fonts) / [Noto CJK](https://github.com/notofonts/noto-cjk) | OFL-1.1 |
| ocrs-cjk engine | [kent-tokyo/ocrs-cjk](https://github.com/kent-tokyo/ocrs-cjk) | MIT / Apache-2.0 |
| PdfCraft application icon | [storytold/pdfcraft](https://github.com/storytold/pdfcraft) | MIT OR Apache-2.0 |

---

*This document describes the reasoning behind the project's licence handling. It
is not legal advice.*
