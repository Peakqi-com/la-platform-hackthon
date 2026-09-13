"""首頁頁尾 logo：原始檔（repo 根目錄 Logo/，不進 git）→ public/city-wind/logos/*.png。

每張都做三件事：
1. 去背：白底／黑底從圖邊灌水找出背景，背景透明；筆畫邊緣的半透明像素用鄰近實色還原顏色，
   不留白邊或黑邊。已經是透明底的原檔跳過這步。標誌內部被圍住的白色是圖案（地政局的手、
   新北市政府花瓣的白心），保留；只有網點之間露出的紙色當背景。
2. 字轉白：以最寬的空白欄把標誌和文字分開，文字部分的黑、灰（低彩度）像素一律轉白；
   彩色部分（標誌本體、地政局那條橘線、AWS 的橘色微笑）保留原色。
3. 裁到內容外框，高度超過 MAX_H 就等比縮小（頁尾顯示約 30–60 px，留三倍解析度）。

用法（需要 pillow、numpy；backend 的 venv 都有）：
    backend/.venv/Scripts/python frontend/scripts/make_logos.py [--src Logo] [--preview out.png]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend" / "public" / "city-wind" / "logos"
MAX_H = 180
PAGE_BG = (9, 19, 19)  # style.css --bg，預覽用

# 輸出名、原始檔、背景（white／black／None＝原檔已透明）、哪部分是文字（right＝最寬空白欄右側／all）、
# 網點色（標誌用網點表現漸層時，網點之間的白是紙色要透明；None＝沒有網點）
LOGOS = [
    ("land", "20210804192617_27174.png", "white", "right", (135, 110, 160)),
    ("ntpc", "新北市政府LOGO（橫式，原始檔）-1-scaled.jpg", "white", "right", None),
    ("youth", "20231023094145021.png", None, "right", None),
    ("digitimes", "DIGITIMES.png", None, "all", None),
    ("netron", "201b0b39-37db-415b-bbe1-f3e169d1c2bf.png", None, "right", None),
    ("aws", "250703-BN-AWS 10 大熱門服務.png", "black", "all", None),
]

NEAR = 40      # 與背景色的最大通道差小於此值 → 視為背景（JPG 雜訊約 10–20）
BAND = 2       # 背景外圍幾個像素算筆畫邊緣（反鋸齒帶）
NEUTRAL = 48   # 彩度（max-min）小於此值 → 黑白灰，文字部分轉白
SHIFTS8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def shift(a: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """平移且不環繞，空出來的補 0。"""
    out = np.zeros_like(a)
    h, w = a.shape[:2]
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = \
        a[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def dilate(m: np.ndarray, r: int) -> np.ndarray:
    for _ in range(r):
        m = m | np.logical_or.reduce([shift(m, dy, dx) for dy, dx in SHIFTS8])
    return m


def flood_from_border(mask: np.ndarray) -> np.ndarray:
    """mask 中與圖邊四連通的部分。"""
    cur = np.zeros_like(mask)
    cur[0, :], cur[-1, :], cur[:, 0], cur[:, -1] = mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]
    while True:
        prev = cur
        for _ in range(16):
            cur = (cur | shift(cur, 1, 0) | shift(cur, -1, 0) | shift(cur, 0, 1) | shift(cur, 0, -1)) & mask
        if (cur == prev).all():
            return cur


def components(mask: np.ndarray):
    """mask 的四連通區塊，逐一回傳 (ys, xs)。只走 mask 內的像素，數量少，逐點走即可。"""
    h, w = mask.shape
    m = mask.tolist()
    seen = [[False] * w for _ in range(h)]
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0][x0]:
            continue
        seen[y0][x0] = True
        comp, i = [(y0, x0)], 0
        while i < len(comp):
            y, x = comp[i]
            i += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and m[ny][nx] and not seen[ny][nx]:
                    seen[ny][nx] = True
                    comp.append((ny, nx))
        ys, xs = zip(*comp)
        yield np.array(ys), np.array(xs)


def halftone_gaps(inner: np.ndarray, near: np.ndarray, rgb: np.ndarray, color, r: int = 2) -> np.ndarray:
    """被圍住的白色區塊裡，外圍一圈有兩成以上是網點色的（網點之間、網點與色塊之間的縫）。
    面積分不開：地政局網點縫 1–18 px，手的白線碎段 9–28 px；外圍顏色分得開（紫 vs 橘）。"""
    out = np.zeros_like(inner)
    h, w = inner.shape
    for ys, xs in components(inner):
        y0, y1 = max(ys.min() - r, 0), min(ys.max() + r + 1, h)
        x0, x1 = max(xs.min() - r, 0), min(xs.max() + r + 1, w)
        comp = np.zeros((y1 - y0, x1 - x0), bool)
        comp[ys - y0, xs - x0] = True
        ring = dilate(comp, r) & ~comp & ~near[y0:y1, x0:x1]
        if ring.any() and (np.abs(rgb[y0:y1, x0:x1][ring] - color).max(axis=1) < 40).mean() >= 0.2:
            out[ys, xs] = True
    return out


def text_split(ink: np.ndarray) -> int:
    """最寬空白欄的中點（標誌在左、文字在右）。"""
    cols = ink.any(axis=0)
    xs = np.flatnonzero(cols)
    best, at = 0, 0
    for a, b in zip(xs[:-1], xs[1:]):
        if b - a > best:
            best, at = b - a, (a + b) // 2
    return at


def remove_background(rgb: np.ndarray, bg: np.ndarray, text_cols: np.ndarray, halftone) -> tuple[np.ndarray, np.ndarray]:
    """回傳 (還原後顏色, alpha)。"""
    d = np.abs(rgb - bg).max(axis=2)
    near = d < NEAR
    back = flood_from_border(near) | (near & text_cols[None, :])   # 文字部分：字的內部空白也是背景
    if halftone is not None:
        back |= halftone_gaps(near & ~back, near, rgb, np.array(halftone, float))
    band = dilate(back, BAND) & ~back
    solid = ~back & ~band

    # 邊緣帶：從鄰近實色借顏色（去掉混進去的背景色）
    col = np.where(solid[..., None], rgb, 0.0)
    have = solid.copy()
    for _ in range(BAND + 3):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(have.shape)
        for dy, dx in SHIFTS8:
            h = shift(have, dy, dx)
            acc += shift(col, dy, dx) * h[..., None]
            cnt += h
        new = band & ~have & (cnt > 0)
        col[new] = acc[new] / cnt[new][:, None]
        have |= new

    alpha = np.ones(d.shape)
    ref = np.abs(col - bg).max(axis=2)
    ok = band & have
    alpha[ok] = np.clip(d[ok] / np.maximum(ref[ok], 1), 0, 1)
    # 太細、借不到實色的筆畫：color-to-alpha
    thin = band & ~have
    a = d[thin] / 255
    alpha[thin] = a
    col[thin] = bg + (rgb[thin] - bg) / np.maximum(a, 1e-3)[:, None]
    alpha[back] = 0
    alpha[alpha < 0.04] = 0
    return np.clip(col, 0, 255), alpha


def process(src: Path, background: str | None, text: str, halftone=None) -> tuple[Image.Image, int]:
    im = Image.open(src).convert("RGBA")
    arr = np.asarray(im).astype(np.float64)
    rgb, alpha = arr[..., :3], arr[..., 3] / 255
    h, w = alpha.shape

    if background:
        bg = np.array([255.0] * 3 if background == "white" else [0.0] * 3)
        ink = np.abs(rgb - bg).max(axis=2) >= NEAR
    else:
        ink = alpha > 0.1
    split = text_split(ink) if text == "right" else 0
    text_cols = np.arange(w) >= split

    if background:
        rgb, alpha = remove_background(rgb, bg, text_cols, halftone)

    # 文字部分的黑白灰轉白（alpha 不動）
    neutral = (rgb.max(axis=2) - rgb.min(axis=2)) < NEUTRAL
    rgb[neutral & text_cols[None, :]] = 255

    out = np.dstack([rgb, alpha * 255]).round().clip(0, 255).astype(np.uint8)
    img = Image.fromarray(out, "RGBA")
    img = img.crop(img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
    if img.height > MAX_H:
        img = img.resize((round(img.width * MAX_H / img.height), MAX_H), Image.LANCZOS)
    return img, split


def preview(images: list[tuple[str, Image.Image]], path: Path, height: int = 96) -> None:
    pad = 28
    rows = [im.resize((round(im.width * height / im.height), height), Image.LANCZOS) for _, im in images]
    sheet = Image.new("RGB", (max(r.width for r in rows) + pad * 2, (height + pad) * len(rows) + pad), PAGE_BG)
    y = pad
    for r in rows:
        sheet.paste(r, (pad, y), r)
        y += height + pad
    sheet.save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ROOT / "Logo")
    ap.add_argument("--preview", type=Path)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    done = []
    for name, file, background, text, halftone in LOGOS:
        img, split = process(args.src / file, background, text, halftone)
        img.save(OUT / f"{name}.png", optimize=True)
        done.append((name, img))
        print(f"{name:10s} {img.width}x{img.height}  text from x={split}")
    if args.preview:
        preview(done, args.preview)


if __name__ == "__main__":
    main()
