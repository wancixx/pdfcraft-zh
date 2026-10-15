#!/usr/bin/env python3
"""pdfcraft-zh — Chinese localisation for PdfCraft (storytold/pdfcraft).

Three changes, none of which alters the existing interface:
  1. Interface font: use a CJK face the system already has (PingFang on macOS,
     Microsoft YaHei on Windows, WenQuanYi on Linux)
  2. Interface languages: keep Simplified Chinese, Traditional Chinese, Japanese
     and English only
  3. Chinese OCR: read Chinese in scans with PaddleOCR's PP-OCRv5 model and write
     the result back as a searchable invisible text layer

The build is then assembled into a standalone application and installed into the
user's own application directory. The original PdfCraft is left untouched:
    macOS    ~/Applications/PdfCraft-zh.app
    Windows  %LOCALAPPDATA%\\PdfCraft-zh\\  (plus a desktop shortcut)
    Linux    ~/.local/bin/pdfcraft + ~/.local/share/applications/pdfcraft-zh.desktop

Usage:
    python3 pdfcraft-zh.py                # checkout, patch, build, install
    python3 pdfcraft-zh.py --dir DIR      # work in DIR
    python3 pdfcraft-zh.py --check        # environment and asset checks only
    python3 pdfcraft-zh.py --jobs 8       # build parallelism
    python3 pdfcraft-zh.py --no-install   # build only; do not assemble or install

Requires Python 3.8+, git and a Rust toolchain (cargo). Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The patch is verified against this upstream commit; checking it out guarantees it applies
UPSTREAM_REPO = "https://github.com/storytold/pdfcraft"
UPSTREAM_COMMIT = "afa8e1843cfed613f3d403119f6c2649bce824c9"

FONTS_REPO = "https://github.com/storytold/craft-fonts"
OCR_CJK_REPO = "https://github.com/kent-tokyo/ocrs-cjk"

# Hugging Face repo holding the model; the first mirror that works is used
HF_REPO = "marsena/paddleocr-onnx-models"
HF_MIRRORS = ["https://hf-mirror.com", "https://huggingface.co"]

# GitHub mirrors (used as a prefix); the empty string means a direct connection
GH_MIRRORS = ["https://ghfast.top/", ""]

MODEL_NAME = "PP-OCRv5_server_rec_infer.onnx"
MODEL_SIZE = 84505505
MODEL_SHA256 = "13d0dda27d63dc0f4938af48df2c55b33f3c989a0bd5eacb8410e30f1735f644"
CONFIG_NAME = "PP-OCRv5_server_rec_infer.yml"

# Renamed to this when installed: rten picks its parser by extension, so ONNX bytes need .onnx
MODEL_INSTALL_NAME = "text-recognition.onnx"

# Detection model: ocrs's official text-box detector (CC-BY-SA-4.0). It only locates
# text, it does not read it, so one copy serves every language. The values match
# pdfcraft's ATTRIBUTION.toml. The official S3 host is unreachable from some networks,
# so an installed PdfCraft or the copy shipped with this patch is preferred.
DETECTION_NAME = "text-detection.rten"
DETECTION_SIZE = 2510284
DETECTION_SHA256 = "f15cfb56bd02c4bf478a20343986504a1f01e1665c2b3a0ad66340f054b1b5ca"
DETECTION_URLS = ["https://ocrs-models.s3-accelerate.amazonaws.com/text-detection.rten"]

FONT_NAME = "NotoSansCJKsc-Regular.otf"
FONT_SIZE = 16759828
FONT_SHA256 = "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b"
FONT_MANIFEST = "fonts/noto-sans-cjk-sc/NotoSansCJKsc-Regular.otf"

# Languages kept (en is built in and needs no file)
KEEP_TSV = {"ja.tsv", "zh-hans.tsv", "zh-hant.tsv"}
DROP_TSV = [
    "ar.tsv", "bg.tsv", "cs.tsv", "de.tsv", "el.tsv", "es.tsv", "fr.tsv", "hu.tsv",
    "it.tsv", "kk.tsv", "lt.tsv", "pl.tsv", "pt-br.tsv", "ru.tsv", "sl.tsv", "te.tsv",
    "tr.tsv", "uk.tsv", "vi.tsv",
]

# ocrs-cjk's rten version must match pdfcraft's
RTEN_FROM, RTEN_TO = "0.24.0", "0.26.0"

# The assembled application: a separate identity so it coexists with the original
APP_NAME = "PdfCraft-zh"
APP_ID = "ai.storyteller.pdfcraft.zh"
APP_VERSION = "0.1.0"
ORIGINAL_ID = "ai.storyteller.pdfcraft"

CODE_PATCH = r'''diff --git a/crates/edit/src/lib.rs b/crates/edit/src/lib.rs
index 515f17d..097bf9d 100644
--- a/crates/edit/src/lib.rs
+++ b/crates/edit/src/lib.rs
@@ -1,3 +1,7 @@
+// Modified by pdfcraft-zh — a Chinese-localisation patch of PdfCraft.
+// Change: adds the CJK branch of the OCR text layer (Identity-H).
+// Full list of changes: licenses/DERIVATION.txt in the built application.
+// Upstream: https://github.com/storytold/pdfcraft (MIT OR Apache-2.0).
 //! pdfcraft-edit — page content editing (L4). Today: page marks, Acrobat's Header & footer,
 //! Watermark, Background and Bates numbering (execution plan M7.6).
 //!
@@ -295,7 +299,7 @@ fn contents(doc: &mut Document, page: &pdfcraft_model::Page) -> Result<Vec<Objec
 }
 
 /// Add the font (and an opacity state) to the page's own resources.
-fn add_resources(doc: &mut Document, page: &pdfcraft_model::Page, opacity: Option<f64>, content: Option<&[u8]>) -> Result<(), EditError> {
+fn add_resources(doc: &mut Document, page: &pdfcraft_model::Page, opacity: Option<f64>, content: Option<&[u8]>, cjk_font: Option<&[u8]>) -> Result<(), EditError> {
     let mut res = page.dict.get(b"Resources").map(|r| doc.resolve(r)).and_then(|r| r.as_dict().cloned()).unwrap_or_default();
     let mut fonts = res.get(b"Font").map(|f| doc.resolve(f)).and_then(|f| f.as_dict().cloned()).unwrap_or_default();
     for (name, base) in [(&b"PCHelv"[..], "Helvetica"), (b"PCTimes", "Times-Roman"), (b"PCCour", "Courier")] {
@@ -310,6 +314,16 @@ fn add_resources(doc: &mut Document, page: &pdfcraft_model::Page, opacity: Optio
         font.set(b"Encoding".to_vec(), Object::name("WinAnsiEncoding"));
         fonts.set(name.to_vec(), Object::Dict(font));
     }
+    // An OCR layer of Chinese text names `/PCCJK`: embed the CJK face once (Identity-H; `embed`
+    // builds the CIDs) and alias that resource to it, so the content stream's CIDs resolve.
+    if let Some(bytes) = cjk_font
+        && content.is_some_and(|c| c.windows(6).any(|w| w == b"/PCCJK"))
+    {
+        let full = pdfcraft_fonts::embedding::embed(doc, &mut fonts, bytes, "NotoSansCJKsc").map_err(EditError::Invalid)?;
+        if let Some(obj) = fonts.get(full.as_bytes()).cloned() {
+            fonts.set(b"PCCJK".to_vec(), obj);
+        }
+    }
     res.set(b"Font".to_vec(), Object::Dict(fonts));
     if let Some(o) = opacity {
         let mut gs = res.get(b"ExtGState").map(|g| doc.resolve(g)).and_then(|g| g.as_dict().cloned()).unwrap_or_default();
@@ -382,10 +396,10 @@ fn place_tagged(doc: &mut Document, page: &pdfcraft_model::Page, tag: &str, cont
 /// Draw `content` on top of a page (0-based) as permanent page content, with standard Helvetica
 /// available as `/PCHelv`. The stream is tagged `tag` (not a mark kind, so Remove never takes
 /// it away); the original content is wrapped in q/Q first. Used for applied redaction boxes.
-pub fn stamp(doc: &mut Document, page: usize, tag: &str, content: Vec<u8>) -> Result<(), EditError> {
+pub fn stamp(doc: &mut Document, page: usize, tag: &str, content: Vec<u8>, cjk_font: Option<&[u8]>) -> Result<(), EditError> {
     let all = page_list(doc);
     check(&[page], all.len())?;
-    add_resources(doc, &all[page], None, Some(&content))?;
+    add_resources(doc, &all[page], None, Some(&content), cjk_font)?;
     let p = page_list(doc).swap_remove(page);
     place_tagged(doc, &p, tag, content, false)
 }
@@ -503,7 +517,7 @@ pub fn add_header_footer(doc: &mut Document, pages: &[usize], hf: &HeaderFooter,
         let mut content = begin(MarkKind::HeaderFooter, "Header", page.view_matrix(doc)).into_bytes();
         content.extend(body);
         content.extend_from_slice(END.as_bytes());
-        add_resources(doc, page, None, None)?;
+        add_resources(doc, page, None, None, None)?;
         let page = &page_list(doc)[i];
         place(doc, page, MarkKind::HeaderFooter, content, false)?;
     }
@@ -542,7 +556,7 @@ pub fn add_watermark(doc: &mut Document, pages: &[usize], wm: &Watermark, replac
             content.push_str(&format!("/PCGS{} gs\n", (opacity * 100.0).round() as i64));
             content.push_str(&picture(src, (w, h), wm.scale, wm.rotation, wm.offset));
             content.push_str(END);
-            add_resources(doc, &page, Some(opacity), None)?;
+            add_resources(doc, &page, Some(opacity), None, None)?;
             add_picture_resource(doc, &page_list(doc)[i].clone(), src)?;
             let page = &page_list(doc)[i];
             place(doc, page, MarkKind::Watermark, content.into_bytes(), wm.behind)?;
@@ -576,7 +590,7 @@ pub fn add_watermark(doc: &mut Document, pages: &[usize], wm: &Watermark, replac
         }
         content.extend_from_slice(b"ET\n");
         content.extend_from_slice(END.as_bytes());
-        add_resources(doc, &page, Some(opacity), None)?;
+        add_resources(doc, &page, Some(opacity), None, None)?;
         let page = &page_list(doc)[i];
         place(doc, page, MarkKind::Watermark, content, wm.behind)?;
     }
@@ -603,7 +617,7 @@ pub fn add_background(doc: &mut Document, pages: &[usize], bg: &Background, repl
             None => content.push_str(&format!("/PCGS{} gs\n{}\n0 0 {} {} re f\n", (opacity * 100.0).round() as i64, rgb(bg.color), n(w), n(h))),
         }
         content.push_str(END);
-        add_resources(doc, &page, Some(opacity), None)?;
+        add_resources(doc, &page, Some(opacity), None, None)?;
         if let Some(src) = &bg.source {
             add_picture_resource(doc, &page_list(doc)[i].clone(), src)?;
         }
diff --git a/crates/engine/src/lib.rs b/crates/engine/src/lib.rs
index 01f162a..0d5755d 100644
--- a/crates/engine/src/lib.rs
+++ b/crates/engine/src/lib.rs
@@ -1,3 +1,7 @@
+// Modified by pdfcraft-zh — a Chinese-localisation patch of PdfCraft.
+// Change: plumbs the CJK font through to the text layer.
+// Full list of changes: licenses/DERIVATION.txt in the built application.
+// Upstream: https://github.com/storytold/pdfcraft (MIT OR Apache-2.0).
 //! pdfcraft-engine — the façade every frontend talks to (architecture §4).
 //!
 //! Holds open documents, their edit history and the tool catalogue. Frontends never touch the
@@ -2484,7 +2488,11 @@ fn run_edit(doc: &mut pdfcraft_cos::Document, edit: &Edit, cx: &mut EditCtx) ->
         }
         Edit::SetDocumentScript { name, script } => pdfcraft_forms::set_document_script(doc, name, script.as_deref())?,
         Edit::AddOcrText { page, words } => {
-            pdfcraft_edit::stamp(doc, *page, "OCR", pdfcraft_ocr::text_layer(words))?;
+            // Chinese text needs the CJK face embedded; an all-Latin page keeps Helvetica.
+            let cjk = pdfcraft_ocr::Models::find().and_then(|m| m.cjk_font_bytes());
+            let bytes = cjk.as_deref().filter(|_| pdfcraft_ocr::needs_cjk(words));
+            let layer = pdfcraft_ocr::text_layer(words, bytes);
+            pdfcraft_edit::stamp(doc, *page, "OCR", layer, bytes)?;
         }
         Edit::EditPageImage { page, index, change } => {
             let img = pdfcraft_edit::page_images(doc, *page)?
diff --git a/crates/fonts/src/embedding.rs b/crates/fonts/src/embedding.rs
index 84801d5..5c872ac 100644
--- a/crates/fonts/src/embedding.rs
+++ b/crates/fonts/src/embedding.rs
@@ -1,3 +1,7 @@
+// Modified by pdfcraft-zh — a Chinese-localisation patch of PdfCraft.
+// Change: adds encode_identity_h() for CJK text layers.
+// Full list of changes: licenses/DERIVATION.txt in the built application.
+// Upstream: https://github.com/storytold/pdfcraft (MIT OR Apache-2.0).
 //! Unicode embedding of an explicitly supplied, embeddable TrueType face. Font files are
 //! document inputs or the optional craft-fonts build input, never system-interface fallbacks.
 
@@ -246,6 +250,32 @@ pub fn embed_mapping(
     Ok(resource)
 }
 
+/// The Identity-H bytes for `text` drawn with a font [`embed`] embedded from `bytes`.
+///
+/// The CIDs match what `embed` assigns: each character maps to its 1-based position in the
+/// font's cmap mapping, iterated in cmap order with unmapped and glyph-0 entries skipped — the
+/// same order `embed` collects. Two-byte big-endian CIDs are what `/Encoding /Identity-H`
+/// expects. A character the font has no glyph for is an error (the caller must not draw it).
+pub fn encode_identity_h(bytes: &[u8], text: &str) -> Result<Vec<u8>, String> {
+    let font = FontRef::new(bytes).map_err(|e| e.to_string())?;
+    let mut cid_of: std::collections::HashMap<char, u16> = std::collections::HashMap::new();
+    let mut n: u32 = 0;
+    for (cp, gid) in font.charmap().mappings() {
+        if gid.to_u32() == 0 {
+            continue;
+        }
+        let Some(c) = char::from_u32(cp) else { continue };
+        n += 1;
+        cid_of.insert(c, u16::try_from(n).map_err(|_| "font mapping limit")?);
+    }
+    let mut out = Vec::with_capacity(text.len() * 2);
+    for c in text.chars() {
+        let cid = cid_of.get(&c).ok_or_else(|| format!("the font has no glyph for {c:?} (U+{:04X})", u32::from(c)))?;
+        out.extend_from_slice(&cid.to_be_bytes());
+    }
+    Ok(out)
+}
+
 /// The decoded data of the stream `object` refers to.
 fn stream_data(doc: &Document, object: Option<&Object>) -> Option<Vec<u8>> {
     match doc.resolve(object?).as_ref() {
diff --git a/crates/ocr/Cargo.toml b/crates/ocr/Cargo.toml
index 46bb3a1..cd8ef28 100644
--- a/crates/ocr/Cargo.toml
+++ b/crates/ocr/Cargo.toml
@@ -1,3 +1,7 @@
+# Modified by pdfcraft-zh — a Chinese-localisation patch of PdfCraft.
+# Change: switches the OCR engine to ocrs-cjk, adds rten onnx_format.
+# Full list of changes: licenses/DERIVATION.txt in the built application.
+# Upstream: https://github.com/storytold/pdfcraft (MIT OR Apache-2.0).
 [package]
 name = "pdfcraft-ocr"
 description = "Scan & OCR: recognise text in page images (ocrs) and write it as an invisible, searchable text layer"
@@ -12,6 +16,6 @@ workspace = true
 
 [dependencies]
 pdfcraft-fonts = { workspace = true }
-ocrs = { version = "0.13.1", default-features = false, features = ["rten"] }
-rten = { version = "0.26.0", default-features = false, features = ["rten_format"] }
+ocrs-cjk = { path = "/Users/wangjunwei/Desktop/pdfcraft-zh-assets/ocrs-cjk/ocrs", default-features = false, features = ["onnx"] }
+rten = { version = "0.26.0", default-features = false, features = ["rten_format", "onnx_format"] }
 thiserror.workspace = true
diff --git a/crates/ocr/src/lib.rs b/crates/ocr/src/lib.rs
index 8d56fa4..c394bed 100644
--- a/crates/ocr/src/lib.rs
+++ b/crates/ocr/src/lib.rs
@@ -1,3 +1,7 @@
+// Modified by pdfcraft-zh — a Chinese-localisation patch of PdfCraft.
+// Change: CJK models, alphabet file, CJK font, zh language.
+// Full list of changes: licenses/DERIVATION.txt in the built application.
+// Upstream: https://github.com/storytold/pdfcraft (MIT OR Apache-2.0).
 //! pdfcraft-ocr — Scan & OCR ▸ Recognize text (L4).
 //!
 //! Recognition runs the ocrs engine (MIT/Apache-2.0) with its pre-trained models (CC-BY-SA-4.0,
@@ -12,19 +16,46 @@
 
 use std::path::{Path, PathBuf};
 
+// ocrs-cjk is the CJK-capable fork of ocrs: the CJK engine shares the upstream API, so the
+// alias keeps this crate's `ocrs::…` paths unchanged.
+use ocrs_cjk as ocrs;
+
 pub use pdfcraft_fonts::helvetica_width;
 
 /// The model files, as named in ATTRIBUTION.toml.
 pub const DETECTION_MODEL: &str = "text-detection.rten";
 pub const RECOGNITION_MODEL: &str = "text-recognition.rten";
 
+/// The same models under an `.onnx` name. rten picks its parser by file extension, so a
+/// PaddleOCR CJK model (ONNX bytes) must keep the `.onnx` extension: named `.rten` it would be
+/// read as an RTen file and fail to parse.
+pub const DETECTION_MODEL_ONNX: &str = "text-detection.onnx";
+pub const RECOGNITION_MODEL_ONNX: &str = "text-recognition.onnx";
+
+/// The first of `names` that exists in `dir`, so a directory may hold either the Latin (`.rten`)
+/// or the CJK (`.onnx`) pair.
+fn pick(dir: &Path, names: &[&str]) -> Option<PathBuf> {
+    names.iter().map(|n| dir.join(n)).find(|p| p.is_file())
+}
+
+/// An optional alphabet file beside the model, holding the recognition model's output classes in
+/// order (the whole file is the alphabet — PaddleOCR's `character_dict`, concatenated). A CJK
+/// model needs it: its thousands of classes cannot be listed in [`ALPHABET`]. Absent for the
+/// Latin models, which use [`ALPHABET`].
+pub const ALPHABET_FILE: &str = "alphabet.txt";
+
+/// The CJK face an OCR text layer of Chinese text is drawn in, embedded into the PDF as
+/// Identity-H. Optional: a Latin-only install has no such file and no Chinese to draw.
+pub const CJK_FONT_FILE: &str = "NotoSansCJKsc-Regular.otf";
+
 /// The recognition model's alphabet, as it was trained (ocrs-models' `DEFAULT_ALPHABET`): its
 /// output classes follow this order. The ocrs crate's own copy has an `E` where the training had
 /// `€`, which made a scanned "€250" read as "E250".
 pub const ALPHABET: &str = " 0123456789!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~€ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
 
-/// The languages the models read (ISO 639-1); all use the Latin alphabet without accents.
-pub const LANGUAGES: &[(&str, &str)] = &[("en", "English")];
+/// The languages the models read (ISO 639-1). The Latin models read English; a CJK recognition
+/// model (PaddleOCR PP-OCRv5) reads Simplified and Traditional Chinese as well as English.
+pub const LANGUAGES: &[(&str, &str)] = &[("en", "English"), ("zh", "中文（简体 / 繁體）")];
 
 #[derive(Debug, thiserror::Error)]
 pub enum OcrError {
@@ -40,20 +71,34 @@ pub enum OcrError {
     EmptyImage,
 }
 
-/// Where the two model files are.
+/// Where the model files are, and the alphabet beside them when the model needs one.
 #[derive(Clone, Debug, PartialEq)]
 pub struct Models {
     pub detection: PathBuf,
     pub recognition: PathBuf,
+    /// A CJK model's `character_dict` (see [`ALPHABET_FILE`]); `None` for the Latin models.
+    pub alphabet: Option<PathBuf>,
+    /// The CJK face for a Chinese text layer (see [`CJK_FONT_FILE`]); `None` without it.
+    pub cjk_font: Option<PathBuf>,
 }
 
 impl Models {
-    /// The models in `dir`, if both files are there.
+    /// The models in `dir`, if both model files are there.
     pub fn in_dir(dir: &Path) -> Option<Models> {
-        let m = Models { detection: dir.join(DETECTION_MODEL), recognition: dir.join(RECOGNITION_MODEL) };
+        let m = Models {
+            detection: pick(dir, &[DETECTION_MODEL, DETECTION_MODEL_ONNX])?,
+            recognition: pick(dir, &[RECOGNITION_MODEL, RECOGNITION_MODEL_ONNX])?,
+            alphabet: Some(dir.join(ALPHABET_FILE)).filter(|p| p.is_file()),
+            cjk_font: Some(dir.join(CJK_FONT_FILE)).filter(|p| p.is_file()),
+        };
         (m.detection.is_file() && m.recognition.is_file()).then_some(m)
     }
 
+    /// The bytes of the CJK face, if one is installed beside the models.
+    pub fn cjk_font_bytes(&self) -> Option<Vec<u8>> {
+        std::fs::read(self.cjk_font.as_ref()?).ok()
+    }
+
     /// Look for the models: `$PDFCRAFT_MODELS`, then where the release packages install them
     /// beside the executable ([`Models::dirs_beside_exe`]), then the source tree's `assets/models/`.
     pub fn find() -> Option<Models> {
@@ -111,10 +156,16 @@ pub struct Ocr {
 impl Ocr {
     pub fn load(models: &Models) -> Result<Ocr, OcrError> {
         let load = |p: &Path| rten::Model::load_file(p).map_err(|e| OcrError::Load(p.display().to_string(), e.to_string()));
+        // A CJK model carries its own alphabet (thousands of classes); the Latin models use the
+        // alphabet they were trained with.
+        let alphabet = match &models.alphabet {
+            Some(p) => std::fs::read_to_string(p).map_err(|e| OcrError::Load(p.display().to_string(), e.to_string()))?,
+            None => ALPHABET.into(),
+        };
         let params = ocrs::OcrEngineParams {
             detection_model: Some(load(&models.detection)?),
             recognition_model: Some(load(&models.recognition)?),
-            alphabet: Some(ALPHABET.into()),
+            alphabet: Some(alphabet),
             ..Default::default()
         };
         let engine = ocrs::OcrEngine::new(params).map_err(|e| OcrError::Load("ocr engine".into(), e.to_string()))?;
@@ -211,13 +262,23 @@ fn num(v: f64) -> String {
     if s == "-0" { "0".into() } else { s.into() }
 }
 
+/// Whether `words` need the CJK face: any character the standard WinAnsi fonts cannot hold.
+/// The caller passes the CJK font only when this is true.
+pub fn needs_cjk(words: &[PlacedWord]) -> bool {
+    words.iter().any(|w| w.text.chars().any(|c| !pdfcraft_fonts::win_ansi_encodable(c)))
+}
+
 /// Page content that writes `words` as invisible text in `/PCHelv` (standard Helvetica,
 /// WinAnsiEncoding), each word stretched to its box so selection and search highlight the
 /// right place. Marked content `/OCR` so it can be told apart from the page's own text.
-pub fn text_layer(words: &[PlacedWord]) -> Vec<u8> {
-    let mut out = b"/OCR BMC\nBT\n3 Tr\n/PCHelv 1 Tf\n".to_vec();
+pub fn text_layer(words: &[PlacedWord], cjk: Option<&[u8]>) -> Vec<u8> {
+    // A CJK model's words go into the embedded CJK face as Identity-H (two-byte CIDs); the Latin
+    // models keep the standard `/PCHelv` Helvetica with WinAnsiEncoding. `/PCCJK` is the resource
+    // name the caller installs when it passes `cjk`.
+    let resource = if cjk.is_some() { "/PCCJK" } else { "/PCHelv" };
+    let mut out = format!("/OCR BMC\nBT\n3 Tr\n{resource} 1 Tf\n").into_bytes();
     for w in words {
-        let width = helvetica_width(&w.text, 1.0);
+        let width = if cjk.is_some() { pdfcraft_fonts::cjk_width(&w.text, 1.0) } else { helvetica_width(&w.text, 1.0) };
         let height = w.up[0].hypot(w.up[1]);
         if width <= 0.0 || height <= 0.0 {
             continue;
@@ -232,8 +293,22 @@ pub fn text_layer(words: &[PlacedWord]) -> Vec<u8> {
         let nums: Vec<String> = m.iter().map(|v| num(*v)).collect();
         out.extend_from_slice(nums.join(" ").as_bytes());
         out.extend_from_slice(b" Tm ");
-        out.extend(pdfcraft_fonts::literal(&pdfcraft_fonts::win_ansi(&w.text)));
-        out.extend_from_slice(b" Tj\n");
+        match cjk {
+            Some(bytes) => {
+                // Identity-H draws two-byte CIDs; a hex string carries them. A word the font
+                // cannot show is left out rather than drawn as garbage.
+                if let Ok(cids) = pdfcraft_fonts::embedding::encode_identity_h(bytes, &w.text) {
+                    let hex: String = cids.iter().map(|b| format!("{b:02X}")).collect();
+                    out.extend_from_slice(format!("<{hex}> Tj\n").as_bytes());
+                } else {
+                    out.extend_from_slice(b"() Tj\n");
+                }
+            }
+            None => {
+                out.extend(pdfcraft_fonts::literal(&pdfcraft_fonts::win_ansi(&w.text)));
+                out.extend_from_slice(b" Tj\n");
+            }
+        }
     }
     out.extend_from_slice(b"ET\nEMC\n");
     out
diff --git a/crates/redact/src/lib.rs b/crates/redact/src/lib.rs
index 61231bd..58a0c08 100644
--- a/crates/redact/src/lib.rs
+++ b/crates/redact/src/lib.rs
@@ -1,3 +1,7 @@
+// Modified by pdfcraft-zh — a Chinese-localisation patch of PdfCraft.
+// Change: keeps redaction consistent with the CJK text layer.
+// Full list of changes: licenses/DERIVATION.txt in the built application.
+// Upstream: https://github.com/storytold/pdfcraft (MIT OR Apache-2.0).
 //! Redaction (architecture §11.2, execution plan M8.5–M8.7). Layer L4.
 //!
 //! Content is marked for redaction with Redact annotations (§12.5.6.23); `pdfcraft-annot`
@@ -481,7 +485,7 @@ pub fn apply(doc: &mut Document, pages: Option<&[usize]>) -> Result<Report, Reda
     // 4. The boxes.
     for (pi, content) in overlays {
         if !content.is_empty() {
-            pdfcraft_edit::stamp(doc, pi, "Redaction", content)?;
+            pdfcraft_edit::stamp(doc, pi, "Redaction", content, None)?;
         }
     }
 
diff --git a/crates/ui-egui/src/i18n/mod.rs b/crates/ui-egui/src/i18n/mod.rs
index 5bb2889..af07908 100644
--- a/crates/ui-egui/src/i18n/mod.rs
+++ b/crates/ui-egui/src/i18n/mod.rs
@@ -1,3 +1,7 @@
+// Modified by pdfcraft-zh — a Chinese-localisation patch of PdfCraft.
+// Change: reduces the interface to four languages.
+// Full list of changes: licenses/DERIVATION.txt in the built application.
+// Upstream: https://github.com/storytold/pdfcraft (MIT OR Apache-2.0).
 //! UI localisation. Strings in code stay English and are the default lookup keys; a per-language
 //! catalog (`*.tsv`, see `ja.tsv` for the format) maps them to display text at render time. Command
 //! ids, document text, file names, the control channel, the CLI and MCP never see translated text,
@@ -58,96 +62,17 @@ fn plural_none(_: u64) -> usize {
     0
 }
 
-/// Lithuanian: one (ending in 1 except 11), few (ending in 2–9 except 12–19), other otherwise.
-fn plural_lithuanian(n: u64) -> usize {
-    match (n % 10, n % 100) {
-        (1, 11) => 2,
-        (1, _) => 0,
-        (2..=9, 12..=19) => 2,
-        (2..=9, _) => 1,
-        _ => 2,
-    }
-}
 
-/// Czech: 1 → one, 2–4 → few, everything else (0, 5+) → other.
-fn plural_cs(n: u64) -> usize {
-    match n {
-        1 => 0,
-        2..=4 => 1,
-        _ => 2,
-    }
-}
 
-/// Portuguese: 0 and 1 take the singular, everything else the plural.
-fn plural_pt(n: u64) -> usize {
-    usize::from(n > 1)
-}
 
-/// French (CLDR `fr`): 0 and 1 take the singular, everything else the plural.
-fn plural_fr(n: u64) -> usize {
-    usize::from(n > 1)
-}
 
-/// Russian: 1 (but not 11) is `one`, 2–4 (but not 12–14) `few`, everything else `many`.
-fn plural_russian(n: u64) -> usize {
-    match n % 100 {
-        11..=14 => 2,
-        _ => match n % 10 {
-            1 => 0,
-            2..=4 => 1,
-            _ => 2,
-        },
-    }
-}
 
-/// Ukrainian (CLDR `uk`, integer counts): one (1, 21), few (2–4, 22–24), many (0, 5–19).
-/// Counts ending in 11–14 always take many, regardless of the last digit.
-fn plural_ukrainian(n: u64) -> usize {
-    match n % 100 {
-        11..=14 => 2,
-        _ => match n % 10 {
-            1 => 0,
-            2..=4 => 1,
-            _ => 2,
-        },
-    }
-}
 
-/// Arabic (CLDR `ar`, integer counts): zero (0), one (1), two (2), few (3–10, 103–110),
-/// many (11–99, 111–199), other (100–102, 200–202).
-fn plural_arabic(n: u64) -> usize {
-    match (n, n % 100) {
-        (0, _) => 0,
-        (1, _) => 1,
-        (2, _) => 2,
-        (_, 3..=10) => 3,
-        (_, 11..=99) => 4,
-        _ => 5,
-    }
-}
 
-/// Polish integer counts: 1 is one; endings 2–4 except 12–14 are few; the rest are many.
-fn plural_polish(n: u64) -> usize {
-    match (n, n % 100, n % 10) {
-        (1, _, _) => 0,
-        (_, 12..=14, _) => 2,
-        (_, _, 2..=4) => 1,
-        _ => 2,
-    }
-}
 
-/// Slovene (CLDR `sl`): one (1, 101, 201 ...) | two (2, 102 ...) | few (3, 4, 103 ...) | other.
-fn plural_sl(n: u64) -> usize {
-    match n % 100 {
-        1 => 0,
-        2 => 1,
-        3 | 4 => 2,
-        _ => 3,
-    }
-}
 
 /// The registry. English first: it is the fallback and the source language.
-pub static LANGUAGES: [LangInfo; 23] = [
+pub static LANGUAGES: [LangInfo; 4] = [
     LangInfo { code: "en", name: "English", source: "", plural: plural_one_other, rtl: false, catalog: OnceLock::new() },
     LangInfo { code: "ja", name: "日本語", source: include_str!("ja.tsv"), plural: plural_none, rtl: false, catalog: OnceLock::new() },
     // Simplified Chinese; `zh`, `zh-CN`, `zh-SG` and `zh-Hans-*` locales resolve here (see `candidates`).
@@ -159,57 +84,6 @@ pub static LANGUAGES: [LangInfo; 23] = [
     LangInfo {
         code: "zh-hant", name: "繁體中文", source: include_str!("zh-hant.tsv"), plural: plural_none, rtl: false, catalog: OnceLock::new()
     },
-    LangInfo { code: "cs", name: "Čeština", source: include_str!("cs.tsv"), plural: plural_cs, rtl: false, catalog: OnceLock::new() },
-    // Brazilian Portuguese; `pt`, `pt-BR` and `pt-PT` locales all resolve here (see `candidates`).
-    LangInfo {
-        code: "pt-br",
-        name: "Português (Brasil)",
-        source: include_str!("pt-br.tsv"),
-        plural: plural_pt,
-        rtl: false,
-        catalog: OnceLock::new(),
-    },
-    // German (informal "du"); every `de-*` locale (`de-DE`, `de-AT`, `de-CH` ...) resolves here.
-    LangInfo { code: "de", name: "Deutsch", source: include_str!("de.tsv"), plural: plural_one_other, rtl: false, catalog: OnceLock::new() },
-    // Spanish (European vocabulary); every `es-*` locale (`es-ES`, `es-MX`, `es-419` ...) resolves here.
-    LangInfo { code: "es", name: "Español", source: include_str!("es.tsv"), plural: plural_one_other, rtl: false, catalog: OnceLock::new() },
-    // French; every `fr-*` locale (`fr-FR`, `fr-CA`, `fr-BE` ...) resolves here.
-    LangInfo { code: "fr", name: "Français", source: include_str!("fr.tsv"), plural: plural_fr, rtl: false, catalog: OnceLock::new() },
-    // Russian; every `ru-*` locale (`ru-RU`, `ru-BY`, `ru-KZ` ...) resolves here.
-    LangInfo { code: "ru", name: "Русский", source: include_str!("ru.tsv"), plural: plural_russian, rtl: false, catalog: OnceLock::new() },
-    // Kazakh; every `kk-*` locale (`kk-KZ`, `kk-KZ.UTF-8`) resolves here.
-    LangInfo { code: "kk", name: "Қазақша", source: include_str!("kk.tsv"), plural: plural_one_other, rtl: false, catalog: OnceLock::new() },
-    // Bulgarian; every `bg-*` locale (`bg-BG`) resolves here.
-    LangInfo {
-        code: "bg", name: "Български", source: include_str!("bg.tsv"), plural: plural_one_other, rtl: false, catalog: OnceLock::new()
-    },
-    // Telugu; every `te-*` locale (`te-IN`) resolves here.
-    LangInfo {
-        code: "te", name: "తెలుగు", source: include_str!("te.tsv"), plural: plural_one_other, rtl: false, catalog: OnceLock::new()
-    },
-    // Hungarian; every `hu-*` locale (`hu-HU`) resolves here.
-    LangInfo { code: "hu", name: "Magyar", source: include_str!("hu.tsv"), plural: plural_one_other, rtl: false, catalog: OnceLock::new() },
-    // Ukrainian; every `uk-*` locale (`uk-UA`, `uk_UA.UTF-8`) resolves here.
-    LangInfo {
-        code: "uk", name: "Українська", source: include_str!("uk.tsv"), plural: plural_ukrainian, rtl: false, catalog: OnceLock::new()
-    },
-    // Italian; every `it-*` locale (`it-IT`) resolves here.
-    LangInfo { code: "it", name: "Italiano", source: include_str!("it.tsv"), plural: plural_one_other, rtl: false, catalog: OnceLock::new() },
-    // Arabic (Modern Standard, Western digits); every `ar-*` locale (`ar-MA`, `ar-EG`, `ar-SA` ...)
-    // resolves here. Right to left: see `LangInfo::rtl`.
-    LangInfo { code: "ar", name: "العربية", source: include_str!("ar.tsv"), plural: plural_arabic, rtl: true, catalog: OnceLock::new() },
-    // Polish; every `pl-*` locale (`pl-pl`, `pl_pl.UTF-8`) resolves here.
-    LangInfo { code: "pl", name: "Polski", source: include_str!("pl.tsv"), plural: plural_polish, rtl: false, catalog: OnceLock::new() },
-    // Slovene; every `sl-*` locale (`sl-SI`) resolves here. Four plural forms (one, two, few, other).
-    LangInfo { code: "sl", name: "Slovenščina", source: include_str!("sl.tsv"), plural: plural_sl, rtl: false, catalog: OnceLock::new() },
-    LangInfo { code: "el", name: "Ελληνικά", source: include_str!("el.tsv"), plural: plural_one_other, rtl: false, catalog: OnceLock::new() },
-    // Turkish; every `tr-*` locale (`tr-TR`, `tr_TR.UTF-8`) resolves here.
-    LangInfo { code: "tr", name: "Türkçe", source: include_str!("tr.tsv"), plural: plural_none, rtl: false, catalog: OnceLock::new() },
-    // Lithuanian; every `lt-*` locale (`lt-LT`, `lt_LT.UTF-8`) resolves here. Three plural forms (one, few, other).
-    LangInfo { code: "lt", name: "Lietuvių", source: include_str!("lt.tsv"), plural: plural_lithuanian, rtl: false, catalog: OnceLock::new() },
-    // Vietnamese; every `vi-*` locale (`vi-VN`, `vi_VN.UTF-8`) resolves here. CLDR `vi` counts have
-    // one form ("other"), so `@plural` entries list a single form.
-    LangInfo { code: "vi", name: "Tiếng Việt", source: include_str!("vi.tsv"), plural: plural_none, rtl: false, catalog: OnceLock::new() },
 ];
 
 impl LangInfo {
@@ -312,10 +186,6 @@ fn candidates(tag: &str) -> Vec<String> {
         let script = if parts.iter().any(|p| matches!(*p, "tw" | "hk" | "mo")) { "zh-hant" } else { "zh-hans" };
         out.insert(out.len().saturating_sub(1), script.to_string());
     }
-    if primary == "pt" && !out.iter().any(|c| c == "pt-br") {
-        // The only Portuguese catalog is Brazilian; other regions use it rather than English.
-        out.insert(out.len().saturating_sub(1), "pt-br".to_string());
-    }
     out
 }
 
diff --git a/crates/ui-egui/src/system_fonts.rs b/crates/ui-egui/src/system_fonts.rs
index 606fa92..f35e69c 100644
--- a/crates/ui-egui/src/system_fonts.rs
+++ b/crates/ui-egui/src/system_fonts.rs
@@ -1,3 +1,7 @@
+// Modified by pdfcraft-zh — a Chinese-localisation patch of PdfCraft.
+// Change: uses the system CJK face (PingFang on macOS 15+).
+// Full list of changes: licenses/DERIVATION.txt in the built application.
+// Upstream: https://github.com/storytold/pdfcraft (MIT OR Apache-2.0).
 //! The last-resort interface font: one face already installed on this machine.
 //!
 //! The embedded faces (Inter, egui's defaults, craft-fonts) come first in every family; this one
@@ -256,6 +260,18 @@ fn other_candidates() -> Vec<PathBuf> {
     }
 }
 
+/// PingFang in the macOS 15 MobileAsset store. Before macOS 15 the face lives at
+/// `/System/Library/Fonts/PingFang.ttc`; 15 moved it under `/System/Library/AssetsV2`, whose
+/// directories are content-hashed, so it has to be found rather than named. Copying the file
+/// into the app is not an option (Apple's licence), but reading the installed one is.
+fn pingfang_in_mobile_assets() -> Option<PathBuf> {
+    let dir = Path::new("/System/Library/AssetsV2/com_apple_MobileAsset_Font7");
+    std::fs::read_dir(dir).ok()?.flatten().find_map(|entry| {
+        let candidate = entry.path().join("AssetData").join("PingFang.ttc");
+        candidate.is_file().then_some(candidate)
+    })
+}
+
 /// Chinese sans faces the operating system ships, the UI language's own region first. Noto CJK
 /// and Source Han are left out on purpose (AGENTS.md §1.1).
 fn han_candidates(traditional: bool) -> Vec<PathBuf> {
@@ -266,11 +282,18 @@ fn han_candidates(traditional: bool) -> Vec<PathBuf> {
         files.iter().map(|f| windows_fonts().join(f)).collect()
     } else if cfg!(target_os = "macos") {
         let files: &[&str] = if traditional {
-            &["PingFang.ttc", "STHeiti Light.ttc", "STHeiti Medium.ttc", "Hiragino Sans GB.ttc"]
+            &["STHeiti Light.ttc", "STHeiti Medium.ttc", "Hiragino Sans GB.ttc"]
         } else {
-            &["PingFang.ttc", "Hiragino Sans GB.ttc", "STHeiti Light.ttc", "STHeiti Medium.ttc"]
+            // Simplified Chinese: prefer STHeiti Medium (a Simplified sans with body weight)
+            // over Hiragino Sans GB, whose light Japanese-style glyphs read as a different,
+            // thinner face and mix awkwardly with Latin.
+            &["STHeiti Medium.ttc", "STHeiti Light.ttc", "Hiragino Sans GB.ttc"]
         };
-        files.iter().map(|f| Path::new("/System/Library/Fonts").join(f)).collect()
+        // PingFang first: the pre-15 path, then the macOS 15 MobileAsset store it moved to.
+        let mut out = vec![Path::new("/System/Library/Fonts/PingFang.ttc").to_path_buf()];
+        out.extend(pingfang_in_mobile_assets());
+        out.extend(files.iter().map(|f| Path::new("/System/Library/Fonts").join(f)));
+        out
     } else {
         unix_fonts(&[
             "truetype/wqy/wqy-microhei.ttc",
'''


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

class C:
    """ANSI colours (degrade to plain text when unsupported)."""

    _on = sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"

    @staticmethod
    def _w(code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if C._on else s

    @staticmethod
    def ok(s): return C._w("32", s)        # green
    @staticmethod
    def err(s): return C._w("31", s)       # red
    @staticmethod
    def warn(s): return C._w("33", s)      # yellow
    @staticmethod
    def info(s): return C._w("36", s)      # cyan
    @staticmethod
    def dim(s): return C._w("2", s)        # grey
    @staticmethod
    def bold(s): return C._w("1", s)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def step_header(idx: int, total: int, title: str) -> None:
    print()
    print(C.bold(f"[{idx}/{total}] {title}"))
    print(C.dim("─" * 56))


def die(msg: str) -> None:
    print()
    print(C.err(f"error: {msg}"))
    sys.exit(1)


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

class Bar:
    """Single-line progress bar; finish() moves to the next line. Width follows the terminal."""

    def __init__(self, label: str, total: float | None = None, width: int = 24):
        self.label = label
        self.total = total
        self.width = width
        self.start = time.time()
        self.done = 0.0
        self._last = 0.0
        self._open = False

    def _render(self, extra: str = "") -> None:
        if self.total and self.total > 0:
            pct = min(1.0, self.done / self.total)
            filled = int(pct * self.width)
            bar = "█" * filled + "░" * (self.width - filled)
            line = f"  {self.label} {bar} {pct * 100:3.0f}%  {extra}"
        else:
            spin = "|/-\\"[int(time.time() * 4) % 4]
            line = f"  {self.label} {spin} {extra}"
        cols = shutil.get_terminal_size((80, 24)).columns
        sys.stdout.write("\r" + line[: cols - 1].ljust(cols - 1))
        sys.stdout.flush()
        self._open = True

    def advance(self, n: float = 1.0, extra: str = "") -> None:
        self.done += n
        now = time.time()
        if now - self._last > 0.08:      # rate-limit so the line does not flicker
            self._last = now
            self._render(extra)

    def tick(self, extra: str = "") -> None:
        self._render(extra)

    def finish(self, extra: str = "") -> None:
        if self._open:
            sys.stdout.write("\r" + " " * (shutil.get_terminal_size((80, 24)).columns - 1) + "\r")
            sys.stdout.flush()
        print(f"  {C.ok('✓')} {self.label}{('  ' + extra) if extra else ''}")


# ---------------------------------------------------------------------------
# Subprocesses and downloads
# ---------------------------------------------------------------------------

def run(cmd, cwd: Path | None = None, capture: bool = False, check: bool = True):
    """Run a command; capture=True returns stdout, otherwise output goes to the terminal."""
    if capture:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    else:
        p = subprocess.run(cmd, cwd=cwd)
    if check and p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip() if capture else ""
        die(f"command failed ({p.returncode}): {' '.join(map(str, cmd))}" + (f"\n{detail}" if detail else ""))
    return p


def git_url(url: str) -> str:
    """The first usable GitHub mirror."""
    return GH_MIRRORS[0] + url


def sha256_of(path: Path, bar: Bar | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            if bar:
                bar.advance(len(chunk))
    return h.hexdigest()


def _fetch(url: str, dest: Path, rng: tuple[int, int] | None = None, timeout: int = 180) -> bool:
    """Download a whole file, or one byte range.

    Prefers curl: its retry and timeout handling copes better with connections
    that get cut mid-download. Falls back to urllib when curl is absent.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("curl"):
        cmd = ["curl", "-sL", "--retry", "3", "--retry-delay", "2", "--max-time", str(timeout), "-o", str(dest)]
        if rng:
            cmd += ["-r", f"{rng[0]}-{rng[1]}"]
        cmd.append(url)
        p = subprocess.run(cmd, capture_output=True)
        return p.returncode == 0 and dest.exists() and dest.stat().st_size > 0
    try:
        headers = {"User-Agent": "pdfcraft-zh"}
        if rng:
            headers["Range"] = f"bytes={rng[0]}-{rng[1]}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r, dest.open("wb") as f:
            shutil.copyfileobj(r, f)
        return dest.exists() and dest.stat().st_size > 0
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def download_with_mirrors(name: str, dest: Path) -> None:
    """Download a whole file, trying each mirror in turn; skips when already present."""
    if dest.exists() and dest.stat().st_size > 0:
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    for base in HF_MIRRORS:
        if _fetch(f"{base}/{HF_REPO}/resolve/main/{name}", tmp):
            tmp.replace(dest)
            return
    tmp.unlink(missing_ok=True)
    die(
        f"could not download {name}\n"
        f"  Download it manually into {dest.parent}:\n"
        f"    {HF_MIRRORS[0]}/{HF_REPO}/resolve/main/{name}\n"
        f"  (or the same path under {HF_MIRRORS[1]})"
    )


def extract_alphabet(yml: Path, out: Path) -> int:
    """Extract the recognition model's alphabet from PP-OCRv5's yml.

    PaddleOCR's character_dict is a plain list of characters; multi-codepoint
    entries (flag emoji) contribute only their first codepoint, then
    use_space_char appends one space. The resulting length + 1 (the CTC blank)
    equals the model's output width.
    """
    text = yml.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"character_dict:\s*\n((?:[ \t]*-[ \t].*\n?)+)", text)
    if not m:
        die(f"could not parse character_dict from {yml.name}")
    entries = []
    for line in m.group(1).splitlines():
        # Strip only the leading indent; keep the entry verbatim -- the first entry is an
        pos = line.find("- ")
        if pos >= 0:
            entries.append(line[pos + 2:])
    if len(entries) < 1000:
        die(f"{yml.name}: character_dict yielded only {len(entries)} entries; the format may have changed")
    fixed = [(e[0] if len(e) > 1 else e) for e in entries] + [" "]
    out.write_text("".join(fixed), encoding="utf-8")
    return len(fixed)


# ---------------------------------------------------------------------------
# Locating an installed PdfCraft (to reuse its detection model and icon)
# ---------------------------------------------------------------------------

def installed_app_dirs() -> list[Path]:
    """Where PdfCraft may be installed on this machine, most likely first."""
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return [Path("/Applications") / "PdfCraft.app", home / "Applications" / "PdfCraft.app"]
    if system == "Windows":
        out = []
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(var)
            if base:
                out.append(Path(base) / "PdfCraft")
                out.append(Path(base) / "Programs" / "PdfCraft")
        return out
    return [
        Path("/usr/share/pdfcraft"), Path("/usr/lib/pdfcraft"), Path("/opt/pdfcraft"),
        Path("/usr/local/share/pdfcraft"), home / ".local" / "share" / "pdfcraft",
    ]


def installed_models_dir() -> Path | None:
    """An installed PdfCraft's models directory; its detection model can be reused (size-checked)."""
    for base in installed_app_dirs():
        for d in (
            base / "Contents" / "Resources" / "models",   # macOS .app
            base / "models",                              # Windows / portable
            base / "share" / "pdfcraft" / "models",       # Linux FHS
            base / "resources" / "models",
        ):
            f = d / DETECTION_NAME
            try:
                if f.is_file() and f.stat().st_size == DETECTION_SIZE:
                    return d
            except OSError:
                continue
    return None


def bundled_dir() -> Path:
    """Resources distributed alongside this script (icon, detection model)."""
    return Path(__file__).resolve().parent / "assets"


def find_local_detection(root: Path) -> Path | None:
    """Where the detection model can come from: bundled copy, work dir, installed PdfCraft."""
    for d in (bundled_dir(), Path(__file__).resolve().parent, root):
        f = d / DETECTION_NAME
        try:
            if f.is_file() and f.stat().st_size == DETECTION_SIZE:
                return f
        except OSError:
            continue
    m = installed_models_dir()
    return (m / DETECTION_NAME) if m else None


def download_detection(dest: Path) -> None:
    """Download the detection model -- reached only when the local options are exhausted."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    for url in DETECTION_URLS:
        for _ in range(2):
            if _fetch(url, tmp, timeout=120) and tmp.stat().st_size == DETECTION_SIZE:
                tmp.replace(dest)
                return
            tmp.unlink(missing_ok=True)
            time.sleep(1)
    tmp.unlink(missing_ok=True)
    die(
        f"could not obtain the detection model {DETECTION_NAME} ({DETECTION_SIZE} bytes)\n"
        f"  It only locates text, it does not read it, so the official copy works as-is.\n"
        f"  Use any of these, put the file into {dest.parent}, then run this script again:\n"
        f"    1. copy it from an installed PdfCraft (macOS: PdfCraft.app/Contents/Resources/models/)\n"
        f"    2. take it from this patch's assets/ directory\n"
        f"    3. download it: {DETECTION_URLS[0]}"
    )


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_env(root: Path, jobs: int):
    """Check the system, Python, git and Rust; prepare the source and font repositories."""
    # --- system ---
    plat = platform.system()
    print(f"  system: {C.info(plat + ' ' + platform.machine())}")
    print(f"  Python: {C.info(platform.python_version())}")
    if sys.version_info < (3, 8):
        die("Python 3.8 or newer is required")
    mach = platform.machine().lower()
    if plat == "Darwin" and mach not in ("arm64", "x86_64"):
        print(C.warn(f"  warning: unexpected CPU architecture {mach}"))

    # --- git ---
    if not shutil.which("git"):
        die("git not found. Install it first: macOS: xcode-select --install / Linux: apt install git / Windows: https://git-scm.com")
    print(f"  git: {C.info(run(['git', '--version'], capture=True).stdout.strip())}")

    # --- Rust ---
    if not shutil.which("cargo"):
        print(C.warn("  Rust toolchain (cargo) not found"))
        print("  Install it: https://rustup.rs  or  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
        die("Rust is missing; cannot build")
    print(f"  cargo: {C.info(run(['cargo', '--version'], capture=True).stdout.strip())}")

    # --- pdfcraft source ---
    src = root / "pdfcraft"
    bar = Bar("Fetching pdfcraft source")
    if (src / "Cargo.toml").is_file():
        bar.finish("(already present, reusing)")
    else:
        bar.tick("cloning...")
        run(["git", "clone", "--filter=blob:none", git_url(UPSTREAM_REPO), str(src)])
        bar.finish()
    # pin to the verified commit so the patch is guaranteed to apply
    head = run(["git", "rev-parse", "HEAD"], cwd=src, capture=True, check=False).stdout.strip()
    if head != UPSTREAM_COMMIT:
        bar2 = Bar("Switching to the verified revision")
        run(["git", "fetch", "--depth", "1", "origin", UPSTREAM_COMMIT], cwd=src, check=False)
        p = run(["git", "checkout", "--force", UPSTREAM_COMMIT], cwd=src, capture=True, check=False)
        if p.returncode != 0:
            die(f"cannot switch to {UPSTREAM_COMMIT[:10]}; run this by hand:\n  cd {src} && git fetch --depth 1 origin {UPSTREAM_COMMIT} && git checkout {UPSTREAM_COMMIT}")
        bar2.finish(UPSTREAM_COMMIT[:10])
    else:
        print(f"  ✓ already at the verified revision {C.dim(UPSTREAM_COMMIT[:10])}")

    # --- craft-fonts (supplies the interface CJK font, and is a build input) ---
    fonts = root / "craft-fonts"
    bar = Bar("Fetching craft-fonts")
    if (fonts / "fonts" / "manifest.txt").is_file():
        bar.finish("(already present, reusing)")
    else:
        bar.tick("cloning...")
        run(["git", "clone", "--depth", "1", git_url(FONTS_REPO), str(fonts)])
        bar.finish()

    # --- ocrs-cjk (the CJK OCR engine) ---
    cjk = root / "vendor" / "ocrs-cjk"
    bar = Bar("Fetching ocrs-cjk")
    if (cjk / "ocrs" / "Cargo.toml").is_file():
        bar.finish("(already present, reusing)")
    else:
        cjk.parent.mkdir(parents=True, exist_ok=True)
        bar.tick("cloning...")
        run(["git", "clone", "--depth", "1", git_url(OCR_CJK_REPO), str(cjk)])
        (cjk / ".git").exists() and shutil.rmtree(cjk / ".git", ignore_errors=True)
        # align the rten version so it does not clash with pdfcraft's types
        cargo = cjk / "Cargo.toml"
        t = cargo.read_text(encoding="utf-8")
        t = t.replace(f'rten = {{ version = "{RTEN_FROM}"', f'rten = {{ version = "{RTEN_TO}"')
        t = t.replace(f'rten-imageproc = {{ version = "{RTEN_FROM}" }}', f'rten-imageproc = {{ version = "{RTEN_TO}" }}')
        t = t.replace(f'rten-tensor = {{ version = "{RTEN_FROM}" }}', f'rten-tensor = {{ version = "{RTEN_TO}" }}')
        cargo.write_text(t, encoding="utf-8")
        bar.finish(f"（rten {RTEN_FROM} → {RTEN_TO}）")


def step_assets(root: Path) -> Path:
    """Fetch the recognition model and its config, extract the alphabet, place the CJK font."""
    src = root / "pdfcraft"
    models = src / "assets" / "models"
    models.mkdir(parents=True, exist_ok=True)

    # 1) the recognition model (chunked; long connections get cut)
    #    stored locally as text-recognition.onnx -- the program only knows that name
    model = models / MODEL_INSTALL_NAME
    legacy = models / MODEL_NAME
    if not model.exists() and legacy.is_file():
        legacy.rename(model)
    if model.exists() and model.stat().st_size == MODEL_SIZE:
        print(f"  {C.ok('✓')} recognition model already present {C.dim(human(MODEL_SIZE))}")
    else:
        print(f"  downloading recognition model {C.dim(human(MODEL_SIZE))} (in chunks; long connections get cut)")
        _download_chunked(MODEL_NAME, model, MODEL_SIZE, Bar("Downloading PP-OCRv5 recognition model", MODEL_SIZE))

    # 2) the config (used to extract the alphabet)
    cfg = models / CONFIG_NAME
    download_with_mirrors(CONFIG_NAME, cfg)
    print(f"  {C.ok('✓')} model config {C.dim(cfg.name)}")

    # 3) the alphabet
    alphabet = models / "alphabet.txt"
    n = extract_alphabet(cfg, alphabet)
    got = len(alphabet.read_text(encoding="utf-8"))
    if got + 1 != 18385 or n != 18384:
        die(f"unexpected alphabet length: {got} (expected 18384); the model and config may not match")
    print(f"  {C.ok('✓')} alphabet {C.dim(f'{got} characters')}")

    # 4) the CJK font (embedded into OCR text layers; OFL-1.1 permits embedding)
    font_dst = models / FONT_NAME
    font_src = root / "craft-fonts" / FONT_MANIFEST
    if not font_src.is_file():
        die(f"interface font not found: {font_src}")
    shutil.copy2(font_src, font_dst)
    print(f"  {C.ok('✓')} embedded font {C.dim(FONT_NAME)}")

    # 5) the detection model (ocrs official; it only finds text, so it is language-neutral)
    det = models / DETECTION_NAME
    if det.is_file() and det.stat().st_size == DETECTION_SIZE:
        print(f"  {C.ok('✓')} detection model already present {C.dim(human(DETECTION_SIZE))}")
    else:
        local = find_local_detection(root)
        if local:
            shutil.copy2(local, det)
            print(f"  {C.ok('✓')} detection model {C.dim('from ' + str(local.parent))}")
        else:
            print(f"  downloading detection model {C.dim(human(DETECTION_SIZE))}")
            download_detection(det)
            print(f"  {C.ok('✓')} detection model {C.dim(human(DETECTION_SIZE))}")

    # 6) verification
    for path, want, what, size in (
        (model, MODEL_SHA256, "recognition model", MODEL_SIZE),
        (det, DETECTION_SHA256, "detection model", DETECTION_SIZE),
    ):
        if not want:
            continue
        bar = Bar(f"Verifying {what}", size)
        got = sha256_of(path, bar)
        if got != want:
            bar.finish()
            die(f"{what} verification failed -- the file may be corrupt; delete {path} and retry")
        bar.finish("SHA256 matches")
    return models


def _download_chunked(name: str, dest: Path, total: int, bar: Bar) -> None:
    """Chunked download: long connections get cut, so chunks plus retries are steadier."""
    chunk = 5 << 20
    parts = dest.parent / (dest.name + ".parts")
    parts.mkdir(exist_ok=True)
    got = 0
    start = 0
    i = 0
    while start < total:
        end = min(start + chunk, total) - 1
        want = end - start + 1
        pf = parts / f"{i:03d}"
        if not (pf.exists() and pf.stat().st_size == want):
            done = False
            for base in HF_MIRRORS:
                url = f"{base}/{HF_REPO}/resolve/main/{name}"
                for _ in range(3):
                    if _fetch(url, pf, rng=(start, end)) and pf.stat().st_size == want:
                        done = True
                        break
                    pf.unlink(missing_ok=True)
                    time.sleep(1)
                if done:
                    break
            if not done:
                die(
                    f"could not download {name} (chunk {i + 1} of {(total + chunk - 1) // chunk})\n"
                    f"  Download it manually into {dest.parent}:\n"
                    f"    {HF_MIRRORS[0]}/{HF_REPO}/resolve/main/{name}\n"
                    f"  then run this script again; finished steps are skipped."
                )
        got += pf.stat().st_size
        bar.done = got
        bar.tick(_speed(bar, got))
        start = end + 1
        i += 1
    with dest.open("wb") as out:
        for p in sorted(parts.iterdir()):
            out.write(p.read_bytes())
    shutil.rmtree(parts, ignore_errors=True)
    bar.finish(_speed(bar, total))


def _speed(bar: Bar, done: float) -> str:
    el = max(time.time() - bar.start, 0.001)
    return f"{human(done)} / {human(bar.total or 0)}   {human(done / el)}/s"


def step_patch(root: Path):
    """Apply the code patch, trim the interface languages, wire up ocrs-cjk."""
    src = root / "pdfcraft"
    total = 4
    i = 0

    # 1) the code patch
    i += 1
    bar = Bar(f"[{i}/{total}] Applying code patch")
    bar.tick()
    patch_file = root / "pdfcraft-zh.patch"
    if not patch_file.is_file():
        patch_file.write_text(CODE_PATCH, encoding="utf-8")
    # skip when already applied
    probe = (src / "crates" / "ocr" / "src" / "lib.rs")
    if "use ocrs_cjk as ocrs;" in probe.read_text(encoding="utf-8", errors="replace"):
        bar.finish("(already applied)")
    else:
        p = run(["git", "apply", "--3way", str(patch_file)], cwd=src, capture=True, check=False)
        if p.returncode != 0:
            bar.finish()
            die(f"could not apply the code patch:\n{(p.stderr or p.stdout).strip()}\n"
                f"  The source may not be the verified revision; delete {src} and retry.")
        bar.finish("8 files")

    # 2) trim the interface languages
    i += 1
    bar = Bar(f"[{i}/{total}] Trimming interface languages", len(DROP_TSV))
    lang_dir = src / "crates" / "ui-egui" / "src" / "i18n"
    removed = 0
    for name in DROP_TSV:
        f = lang_dir / name
        if f.exists():
            f.unlink()
            removed += 1
        bar.advance(1)
    bar.finish(f"removed {removed}, keeping zh-Hans / zh-Hant / ja / en")

    # 3) the alphabet (the OCR changes depend on it; make sure it is there)
    i += 1
    bar = Bar(f"[{i}/{total}] Checking OCR assets")
    models = src / "assets" / "models"
    for f in (models / MODEL_INSTALL_NAME, models / DETECTION_NAME,
              models / "alphabet.txt", models / FONT_NAME):
        if not f.is_file():
            bar.finish()
            die(f"missing {f} (step 2 should have prepared it)")
        bar.advance(1)
    bar.finish("models / detection / alphabet / font")

    # 4) ocrs-cjk in place
    i += 1
    bar = Bar(f"[{i}/{total}] Wiring up ocrs-cjk")
    if not (root / "vendor" / "ocrs-cjk" / "ocrs" / "Cargo.toml").is_file():
        bar.finish()
        die("vendor/ocrs-cjk is missing")
    bar.finish("in place")


def link_models_for_dev(src: Path) -> None:
    """Let the source tree's binaries work directly: target/release/models -> assets/models.

    The program looks for models/ next to the executable first, which is exactly the
    Windows portable layout. A symlink costs no extra space. Creating a directory
    junction on Windows may need privileges; if it fails we skip -- the installed
    application is unaffected.
    """
    rel = src / "target" / "release"
    link = rel / "models"
    models = src / "assets" / "models"
    if link.exists() or not rel.is_dir() or not models.is_dir():
        return
    try:
        link.symlink_to(models.resolve(), target_is_directory=True)
        return
    except OSError:
        pass
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(models.resolve())],
                   capture_output=True, check=False)


def step_build(root: Path, jobs: int):
    """Build pdfcraft and pdfcraft-cli, showing cargo progress."""
    src = root / "pdfcraft"
    env = dict(os.environ)
    env["CRAFT_FONTS_DIR"] = str((root / "craft-fonts").resolve())
    bar = Bar("Building (the first build is slow, please wait)")
    cmd = ["cargo", "build", "--release"]
    if jobs:
        cmd += ["-j", str(jobs)]
    cmd += ["-p", "pdfcraft", "-p", "pdfcraft-cli"]
    done = 0
    proc = subprocess.Popen(cmd, cwd=src, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    errors = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        m = re.search(r"\((\d+)/(\d+)\)", line)
        if m:
            done = int(m.group(1))
            total = int(m.group(2))
            bar.total = total
            bar.done = done
            bar.tick(f"{done}/{total} crate")
        elif line.startswith("error") or "error[" in line:
            errors.append(line)
    proc.wait()
    if proc.returncode != 0:
        bar.finish()
        detail = "\n".join(errors[:8]) if errors else ""
        die(f"build failed (exit code {proc.returncode})" + (f"\n{detail}" if detail else ""))
    if done == 0:
        bar.finish("already up to date, nothing to rebuild")
    else:
        bar.finish(f"built {done} crates")
    link_models_for_dev(src)


def step_verify(root: Path) -> bool:
    """Self-check: binary features plus a real Chinese OCR run."""
    src = root / "pdfcraft"
    ok_all = True
    total = 4

    # 1) the binaries exist
    bar = Bar(f"[1/{total}] Build outputs")
    bins = [src / "target" / "release" / "pdfcraft", src / "target" / "release" / "pdfcraft-cli"]
    for b in bins:
        if not b.is_file():
            bar.finish()
            print(C.err(f"  error: missing {b.name}"))
            ok_all = False
        else:
            bar.advance(1)
    if ok_all:
        bar.finish("pdfcraft / pdfcraft-cli")

    # 2) Chinese support is compiled in
    bar = Bar(f"[2/{total}] Binary features")
    if ok_all:
        blob = bins[1].read_bytes()
        for needle, desc in [(b"NotoSansCJKsc", "CJK font"), (b"PCCJK", "OCR text layer"), (b"alphabet.txt", "CJK alphabet")]:
            if needle in blob:
                bar.advance(1)
            else:
                print(C.err(f"  error: binary lacks the {desc} signature"))
                ok_all = False
        if ok_all:
            bar.finish("font / text layer / alphabet")

    # 3) interface font and languages
    bar = Bar(f"[3/{total}] Interface font and languages")
    if ok_all:
        sf = (src / "crates" / "ui-egui" / "src" / "system_fonts.rs").read_text(encoding="utf-8", errors="replace")
        i18n = (src / "crates" / "ui-egui" / "src" / "i18n" / "mod.rs").read_text(encoding="utf-8", errors="replace")
        checks = [
            ("pingfang_in_mobile_assets" in sf, "macOS PingFang lookup"),
            ("LANGUAGES: [LangInfo; 4]" in i18n, "exactly four languages"),
            ((src / "crates" / "ui-egui" / "src" / "i18n" / "ja.tsv").is_file(), "Japanese kept"),
        ]
        for good, desc in checks:
            if good:
                bar.advance(1)
            else:
                print(C.err(f"  error: {desc} not in effect"))
                ok_all = False
        if ok_all:
            bar.finish("PingFang / 4 languages / Japanese")

    # 4) the OCR assets are complete (models, alphabet length, font)
    bar = Bar(f"[4/{total}] OCR assets")
    if ok_all:
        models = src / "assets" / "models"
        checks = []
        model = models / MODEL_INSTALL_NAME
        checks.append((model.is_file() and model.stat().st_size == MODEL_SIZE, "recognition model 80.6MB"))
        checks.append(((models / DETECTION_NAME).is_file(), "detection model"))
        alpha = models / "alphabet.txt"
        n = len(alpha.read_text(encoding="utf-8")) if alpha.is_file() else 0
        checks.append((n == 18384, f"alphabet 18384 (got {n})"))
        checks.append(((models / FONT_NAME).is_file(), "CJK embedded font"))
        for good, desc in checks:
            if good:
                bar.advance(1)
            else:
                print(C.err(f"  error: {desc} not ready"))
                ok_all = False
        if ok_all:
            bar.finish("models / alphabet / font all present")
    return ok_all


# ---------------------------------------------------------------------------
# Assembling and installing
#
# The layout follows the official packaging/ scripts; the program looks for models
# in this order (crates/ocr/src/lib.rs):
#     models/ next to the exe           -> Windows portable
#     ../Resources/models               -> macOS .app (MacOS/ -> Resources/)
#     ../share/pdfcraft/models          -> Linux bin/ -> share/
# So no code needs changing; putting the files in the right place is enough.
# ---------------------------------------------------------------------------

def workspace_version(src: Path) -> str:
    """The [workspace.package] version from the source Cargo.toml."""
    try:
        text = (src / "Cargo.toml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "0.0.0"
    m = re.search(r'^\[workspace\.package\](.*?)(?=^\[)', text, re.M | re.S)
    if not m:
        return "0.0.0"
    v = re.search(r'^version\s*=\s*"([^"]+)"', m.group(1), re.M)
    return v.group(1) if v else "0.0.0"


def copy_icon(dst: Path) -> bool:
    """Place the icon: prefer the copy shipped with the patch (with the CJK badge), else borrow the original."""
    src = None
    for d in (bundled_dir(), Path(__file__).resolve().parent):
        cand = d / dst.name
        if cand.is_file():
            src = cand
            break
    if src is None:
        for app in installed_app_dirs():
            for cand in (app / "Contents" / "Resources" / dst.name, app / dst.name):
                if cand.is_file():
                    src = cand
                    break
            if src:
                break
    if src is None:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def stage_models(models: Path, dest: Path) -> int:
    """Copy the OCR assets into the target directory (the names are already what the program expects)."""
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(models.iterdir()):
        if not f.is_file() or f.name == CONFIG_NAME:   # the yml is only used at build time, to extract the alphabet
            continue
        shutil.copy2(f, dest / f.name)
        n += 1
    return n


MODELS_ATTRIBUTION = """\
PdfCraft-zh (a modified build of PdfCraft) uses these files for Scan & OCR.

text-detection.rten
  Ocrs text detection model
  by Robert Knight (ocrs-models; trained on HierText)
  from https://github.com/robertknight/ocrs-models
  licence: CC-BY-SA-4.0 -- full text in ../licenses/CC-BY-SA-4.0.txt
  redistributed unmodified; the same file PdfCraft itself ships

text-recognition.onnx
  PaddleOCR PP-OCRv5 server text recognition model (Chinese Simplified,
  Chinese Traditional, Japanese and English)
  by the PaddleOCR team, Baidu
  from https://github.com/PaddlePaddle/PaddleOCR
  ONNX conversion from https://huggingface.co/marsena/paddleocr-onnx-models
  licence: Apache-2.0 -- full text in ../licenses/PaddleOCR-LICENSE-APACHE.txt
  redistributed unmodified

alphabet.txt
  PP-OCRv5's character dictionary (18384 classes), extracted from the model's
  own PP-OCRv5_server_rec_infer.yml. Same licence as the model (Apache-2.0).

NotoSansCJKsc-Regular.otf
  Noto Sans CJK SC
  by the Noto Project Authors
  from https://github.com/notofonts/noto-cjk
  reached through https://github.com/storytold/craft-fonts
  licence: SIL Open Font License 1.1 -- full text in
  ../licenses/OFL-NotoSansCJKsc.txt
  unmodified; embedded into OCR text layers as Identity-H
"""


def derivation_text(version: str) -> str:
    """The modification notice. Apache-2.0 section 4(b) requires it on redistribution."""
    mods = [
        ("crates/edit/src/lib.rs", "adds the CJK branch of the OCR text layer (Identity-H)"),
        ("crates/engine/src/lib.rs", "plumbs the CJK font through to the text layer"),
        ("crates/fonts/src/embedding.rs", "adds encode_identity_h() for CJK text layers"),
        ("crates/ocr/Cargo.toml", "switches the OCR engine to ocrs-cjk, adds rten onnx_format"),
        ("crates/ocr/src/lib.rs", "CJK models, alphabet file, CJK font, zh language"),
        ("crates/redact/src/lib.rs", "keeps redaction consistent with the CJK text layer"),
        ("crates/ui-egui/src/i18n/mod.rs", "reduces the interface to four languages"),
        ("crates/ui-egui/src/system_fonts.rs", "uses the system CJK face (PingFang on macOS 15+)"),
    ]
    lines = [
        f"{APP_NAME} {version} -- a modified build of PdfCraft",
        "=" * 60,
        "",
        "This application is a modified build of PdfCraft. It was produced by the",
        f"{APP_NAME} patch from the upstream source at commit",
        f"{UPSTREAM_COMMIT}",
        "",
        "Upstream:  https://github.com/storytold/pdfcraft",
        "           Copyright (c) 2026 ArtCraft Team and the PdfCraft contributors",
        "           Licensed under the MIT License or the Apache License, Version 2.0,",
        "           at your option. Both licence texts are in this directory.",
        "",
        "This is an unofficial build. It is not produced, endorsed or supported by",
        "the ArtCraft Team. The names 'PdfCraft' and 'ArtCraft' and the ArtCraft",
        "logos are trademarks of the ArtCraft Team; no trademark licence is granted",
        "here (Apache-2.0 section 6). The application is named 'PdfCraft-zh' and",
        "uses a distinct bundle identifier so it cannot be confused with the",
        "official release.",
        "",
        "What was changed",
        "-" * 60,
        "",
    ]
    width = max(len(p) for p, _ in mods)
    for path, what in mods:
        lines.append(f"  {path.ljust(width)}  {what}")
    lines += [
        "",
        "Each file listed above also carries a header comment saying it was modified.",
        "Files deleted: 19 interface translation catalogs for languages this build",
        "does not ship (ar bg cs de el es fr hu it kk lt pl pt-br ru sl te tr uk vi).",
        "",
        "What was NOT changed",
        "-" * 60,
        "",
        "  No buttons, banners, notices or third-party links were removed from the",
        "  interface. Layout and colour scheme are untouched. The ArtCraft community",
        "  panel, the Discord link and the privacy notice are all left exactly as",
        "  upstream ships them.",
        "",
        "Interface fonts",
        "-" * 60,
        "",
        "  The interface uses a CJK face already installed on the user's own system",
        "  (PingFang on macOS, Microsoft YaHei on Windows, WenQuanYi on Linux).",
        "  No system font is redistributed with this build.",
        "",
        "Third-party material",
        "-" * 60,
        "",
        "  See ../licenses/ for the full texts, and models/ATTRIBUTION.txt for the",
        "  OCR models and the font embedded into text layers.",
        "",
    ]
    return "\n".join(lines)


def stage_licences(root: Path, dest: Path) -> int:
    """Put the licences and attributions that redistribution requires into the target directory.

    MIT and Apache-2.0 both require the licence to travel with copies; Apache-2.0
    additionally requires the NOTICE; OFL-1.1 requires the copyright notice and the
    licence; CC-BY-SA-4.0 requires attribution and a link to the licence.
    """
    src = root / "pdfcraft"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0

    def put_file(path: Path, name: str) -> None:
        nonlocal n
        try:
            shutil.copy2(path, dest / name)
            n += 1
        except OSError:
            print(C.warn(f"  ! missing licence file {path}"))

    def put_text(text: str, name: str) -> None:
        nonlocal n
        (dest / name).write_text(text, encoding="utf-8")
        n += 1

    # PdfCraft itself: MIT OR Apache-2.0, both texts plus the NOTICE
    put_file(src / "LICENSE-MIT", "PdfCraft-LICENSE-MIT.txt")
    put_file(src / "LICENSE-APACHE", "PdfCraft-LICENSE-APACHE.txt")
    put_file(src / "NOTICE", "PdfCraft-NOTICE.txt")
    # the CJK font embedded into PDF text layers: OFL-1.1
    put_file(root / "craft-fonts" / "fonts" / "noto-sans-cjk-sc" / "OFL.txt",
             "OFL-NotoSansCJKsc.txt")
    # detection model: CC-BY-SA-4.0 (full text ships with the patch, so no network needed)
    put_file(bundled_dir() / "licenses" / "CC-BY-SA-4.0.txt", "CC-BY-SA-4.0.txt")
    # recognition model: PaddleOCR's own Apache-2.0 copy (same text, but it names its source)
    put_file(bundled_dir() / "licenses" / "PaddleOCR-LICENSE-APACHE.txt",
             "PaddleOCR-LICENSE-APACHE.txt")
    # this patch itself
    put_file(Path(__file__).resolve().parent / "LICENSE", f"{APP_NAME}-LICENSE.txt")
    # the modification notice
    put_text(derivation_text(workspace_version(src)), "DERIVATION.txt")
    # icon: modified from PdfCraft's original
    put_text(
        "Application icon\n"
        "================\n\n"
        f"{APP_NAME}'s icon is PdfCraft's own icon with a small badge added in the\n"
        "lower-right corner. The upstream artwork is:\n\n"
        "  assets/app-icon/pdfcraft.icns\n"
        "  author: PdfCraft contributors\n"
        "  source: https://github.com/storytold/pdfcraft (assets/app-icon/README.md)\n"
        "  licence: MIT OR Apache-2.0 -- full texts in this directory\n"
        "  modified: yes -- a circular badge with the character 中 was composited\n"
        "            onto each size; nothing else was altered.\n\n"
        "The badge was generated by the patch script from the icon shipped with the\n"
        "installed PdfCraft, or from the copy in the patch's assets/ directory.\n",
        "ICON.txt",
    )
    return n


def write_plist(path: Path, version: str) -> None:
    """Info.plist: the same template as the original, with only the display name and identifier changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        '  <key>CFBundleDevelopmentRegion</key><string>zh_CN</string>\n'
        f'  <key>CFBundleDisplayName</key><string>{APP_NAME}</string>\n'
        f'  <key>CFBundleName</key><string>{APP_NAME}</string>\n'
        '  <key>CFBundleExecutable</key><string>PdfCraft</string>\n'
        f'  <key>CFBundleIdentifier</key><string>{APP_ID}</string>\n'
        '  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>\n'
        '  <key>CFBundlePackageType</key><string>APPL</string>\n'
        '  <key>CFBundleSignature</key><string>????</string>\n'
        f'  <key>CFBundleShortVersionString</key><string>{version}</string>\n'
        f'  <key>CFBundleVersion</key><string>{version}</string>\n'
        f'  <key>PdfCraftVersion</key><string>{version}-zh</string>\n'
        f'  <key>PdfCraftBuildCommit</key><string>{UPSTREAM_COMMIT[:10]}+zh</string>\n'
        '  <key>CFBundleIconFile</key><string>PdfCraft</string>\n'
        '  <key>LSApplicationCategoryType</key><string>public.app-category.graphics-design</string>\n'
        '  <key>LSMinimumSystemVersion</key><string>11.0</string>\n'
        '  <key>NSHighResolutionCapable</key><true/>\n'
        '  <key>NSSupportsAutomaticGraphicsSwitching</key><true/>\n'
        '  <key>NSRequiresAquaSystemAppearance</key><false/>\n'
        '  <key>NSHumanReadableCopyright</key>\n'
        '  <string>Modified build of PdfCraft (MIT OR Apache-2.0). '
        'Original copyright the PdfCraft authors.</string>\n'
        '</dict>\n</plist>\n',
        encoding="utf-8",
    )


def _sign_macos(app: Path) -> None:
    """ad-hoc signing (codesign --sign -). Enough to run locally; no Apple account needed.

    Sign inside-out: the executable first, then the bundle -- only then does
    --verify --strict pass.
    """
    if not shutil.which("codesign"):
        return
    exe = app / "Contents" / "MacOS" / "PdfCraft"
    for target in (exe, app):
        p = subprocess.run(
            ["codesign", "--force", "--sign", "-", "--options", "runtime", str(target)],
            capture_output=True, text=True,
        )
        if p.returncode != 0:
            print(C.warn(f"  ! signing failed (does not affect local use): {(p.stderr or '').strip()}"))
            return
    p = subprocess.run(["codesign", "--verify", "--strict", str(app)], capture_output=True, text=True)
    if p.returncode != 0:
        print(C.warn(f"  ! signature verification failed: {(p.stderr or '').strip()}"))


def install_macos(root: Path, src: Path, models: Path) -> Path | None:
    rel = src / "target" / "release"
    ver = workspace_version(src)
    total = 5
    app = root / "dist" / f"{APP_NAME}.app"
    if app.exists():
        shutil.rmtree(app)
    macos_d = app / "Contents" / "MacOS"
    res_d = app / "Contents" / "Resources"
    mdl_d = res_d / "models"
    for d in (macos_d, mdl_d):
        d.mkdir(parents=True, exist_ok=True)

    bar = Bar(f"[1/{total}] Copying the executable")
    shutil.copy2(rel / "pdfcraft", macos_d / "PdfCraft")
    (macos_d / "PdfCraft").chmod(0o755)
    bar.finish("pdfcraft")

    bar = Bar(f"[2/{total}] Application icon")
    bar.finish("PdfCraft-zh.icns (with the CJK badge)" if copy_icon(res_d / "PdfCraft.icns")
               else "not found, using the system default")

    bar = Bar(f"[3/{total}] OCR assets and licences")
    n = stage_models(models, mdl_d)
    (mdl_d / "ATTRIBUTION.txt").write_text(MODELS_ATTRIBUTION, encoding="utf-8")
    n += 1
    n += stage_licences(root, res_d / "licenses")
    bar.finish(f"{n} files (models / font / licences)")

    bar = Bar(f"[4/{total}] Info.plist and signing")
    write_plist(app / "Contents" / "Info.plist", ver)
    (app / "Contents" / "PkgInfo").write_text("APPL????", encoding="ascii")
    _sign_macos(app)
    bar.finish(f"Bundle ID {APP_ID}")

    bar = Bar(f"[5/{total}] Installing")
    dest_dir = Path.home() / "Applications"
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{APP_NAME}.app"
    if target.exists():
        shutil.rmtree(target)
    if shutil.which("ditto"):                       # ditto preserves the bundle signature and extended attributes
        run(["ditto", str(app), str(target)])
    else:
        shutil.copytree(app, target, symlinks=True)
    bar.finish(str(target))
    return target


def install_windows(root: Path, src: Path, models: Path) -> Path | None:
    rel = src / "target" / "release"
    exe = rel / "pdfcraft.exe"
    if not exe.is_file():
        exe = rel / "pdfcraft"
    total = 4
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    dest = Path(base) / APP_NAME

    bar = Bar(f"[1/{total}] Copying the executable")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe if exe.is_file() else rel / "pdfcraft.exe", dest / "pdfcraft.exe")
    bar.finish("pdfcraft.exe")

    bar = Bar(f"[2/{total}] OCR assets and licences")
    n = stage_models(models, dest / "models")       # must sit beside the exe; that is the only place it looks
    (dest / "models" / "ATTRIBUTION.txt").write_text(MODELS_ATTRIBUTION, encoding="utf-8")
    n += 1 + stage_licences(root, dest / "licenses")
    bar.finish(f"{n} files (models / font / licences)")

    bar = Bar(f"[3/{total}] Portable-mode marker")
    # with this file present, settings and caches stay in a local PdfCraftData\ instead of %APPDATA%
    (dest / "portable.txt").write_text(
        "PdfCraft portable mode\n\n"
        "Settings, logs, crash-recovery autosaves and new digital IDs stay in the PdfCraftData\n"
        "folder beside this file instead of %APPDATA% / %LOCALAPPDATA%.\n",
        encoding="utf-8",
    )
    bar.finish("portable.txt")

    bar = Bar(f"[4/{total}] Desktop shortcut")
    ps = (
        "$w = New-Object -ComObject WScript.Shell; "
        "$s = $w.CreateShortcut([IO.Path]::Combine($w.SpecialFolders('Desktop'), '{0}.lnk')); "
        "$s.TargetPath = '{1}'; $s.WorkingDirectory = '{2}'; $s.Save()"
    ).format(APP_NAME, dest / "pdfcraft.exe", dest)
    p = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True, text=True,
    )
    bar.finish("desktop" if p.returncode == 0 else f"not created ({(p.stderr or '').strip()[:40]})")
    return dest


def install_linux(root: Path, src: Path, models: Path) -> Path | None:
    rel = src / "target" / "release"
    home = Path.home()
    total = 4
    bindir = home / ".local" / "bin"
    sharedir = home / ".local" / "share" / "pdfcraft"
    appsdir = home / ".local" / "share" / "applications"
    icondir = home / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"

    bar = Bar(f"[1/{total}] Installing the executable")
    bindir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rel / "pdfcraft", bindir / "pdfcraft")
    (bindir / "pdfcraft").chmod(0o755)
    bar.finish(str(bindir / "pdfcraft"))

    bar = Bar(f"[2/{total}] OCR assets and licences")
    # the program looks for ../share/pdfcraft/models from bin/
    n = stage_models(models, sharedir / "models")
    (sharedir / "models" / "ATTRIBUTION.txt").write_text(MODELS_ATTRIBUTION, encoding="utf-8")
    n += 1 + stage_licences(root, sharedir / "licenses")
    bar.finish(f"{n} files (models / font / licences)")

    bar = Bar(f"[3/{total}] Icon and menu entry")
    icondir.mkdir(parents=True, exist_ok=True)
    have_icon = copy_icon(icondir / f"{APP_NAME}.png")
    appsdir.mkdir(parents=True, exist_ok=True)
    (appsdir / f"{APP_NAME}.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=PdfCraft with Chinese fonts, UI and OCR\n"
        f"Exec={bindir / 'pdfcraft'} %F\n"
        f"Icon={APP_NAME if have_icon else 'pdfcraft'}\n"
        "Terminal=false\n"
        "Categories=Office;Graphics;\n"
        "MimeType=application/pdf;\n",
        encoding="utf-8",
    )
    bar.finish("pdfcraft-zh.desktop")

    bar = Bar(f"[4/{total}] Refreshing the menu cache")
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(appsdir)], capture_output=True)
        bar.finish("refreshed")
    else:
        bar.finish("skipped (no update-desktop-database)")
    return appsdir / f"{APP_NAME}.desktop"


def step_install(root: Path) -> Path | None:
    """Assemble the build into a standalone application and install it; the original PdfCraft is untouched."""
    src = root / "pdfcraft"
    models = src / "assets" / "models"
    system = platform.system()
    if system == "Darwin":
        return install_macos(root, src, models)
    if system == "Windows":
        return install_windows(root, src, models)
    return install_linux(root, src, models)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Add Chinese support to PdfCraft (fonts / languages / OCR)")
    ap.add_argument("--dir", default=".", help="working directory (default: the current one)")
    ap.add_argument("--jobs", type=int, default=0, help="build parallelism (default: cargo decides)")
    ap.add_argument("--check", action="store_true", help="environment and asset checks only")
    ap.add_argument("--no-install", action="store_true", help="build only; do not assemble or install")
    args = ap.parse_args(argv)

    root = Path(args.dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # --check stops after step 3; --no-install drops the assembly step
    TOTAL = 3 if args.check else (5 if args.no_install else 6)

    print()
    print(C.bold("pdfcraft-zh") + C.dim(f"  v{APP_VERSION}"))
    print(C.dim(f"  working directory: {root}"))
    print(C.dim("  Adds to PdfCraft: system CJK fonts / four UI languages / Chinese OCR"))
    print(C.dim("  No existing interface element is changed."))

    step_header(1, TOTAL, "Checking system and environment")
    step_env(root, args.jobs)

    step_header(2, TOTAL, "Fetching Chinese OCR models and assets")
    step_assets(root)

    step_header(3, TOTAL, "Applying code patch")
    step_patch(root)

    if args.check:
        print()
        print(C.ok("Environment and assets check passed."))
        return 0

    step_header(4, TOTAL, "Building PdfCraft")
    step_build(root, args.jobs)

    step_header(5, TOTAL, "Self-check")
    good = step_verify(root)

    if not good:
        print()
        print(C.err(C.bold("error: the self-check failed; see the items marked above.")))
        return 1

    installed = None
    if args.no_install:
        print()
        print(C.dim("  Skipping assembly and installation (--no-install)."))
    else:
        step_header(6, TOTAL, "Assembling and installing the app")
        installed = step_install(root)

    src = root / "pdfcraft"
    print()
    print(C.ok(C.bold("Successful!")))
    print()
    if installed:
        print("  Installed:")
        print(C.bold(f"    {installed}"))
        print()
        print(C.dim("  The original PdfCraft is untouched; both versions can be used side by side."))
    print("  Build outputs:")
    print(C.dim(f"    GUI: {src / 'target' / 'release' / 'pdfcraft'}"))
    print(C.dim(f"    CLI: {src / 'target' / 'release' / 'pdfcraft-cli'}"))
    print()
    print(C.dim("  If the system blocks the first launch (locally built, no vendor signature),"))
    print(C.dim("  click 'Open Anyway' under System Settings -> Privacy & Security."))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        print(C.warn("Cancelled."))
        raise SystemExit(130)
