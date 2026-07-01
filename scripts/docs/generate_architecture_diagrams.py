#!/usr/bin/env python3
"""Generate Hive-Mind architecture diagrams in the neon blueprint style.

The PNGs are committed because README/docs render them directly. Keep this
script as the editable source so future architecture updates do not depend on
manual image editing or generative text rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, sin
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "image"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


PALETTE = {
    "bg": (3, 8, 18),
    "text": (235, 242, 255),
    "muted": (174, 188, 215),
    "purple": (190, 92, 255),
    "blue": (68, 154, 255),
    "cyan": (29, 226, 220),
    "green": (96, 242, 131),
    "yellow": (255, 197, 60),
    "orange": (255, 143, 61),
    "red": (255, 87, 84),
    "pink": (255, 92, 153),
}


@dataclass(frozen=True)
class Card:
    xy: tuple[int, int, int, int]
    color: str
    title: str
    lines: tuple[str, ...] = ()
    icon: str | None = None
    title_size: int = 18
    body_size: int = 14


class NeonCanvas:
    def __init__(self, width: int, height: int, scale: int = 2):
        self.w = width
        self.h = height
        self.s = scale
        self.img = Image.new("RGB", (width * scale, height * scale), PALETTE["bg"])
        self.draw = ImageDraw.Draw(self.img, "RGBA")
        self._background()

    def font(self, size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
        name = "DejaVuSansMono.ttf" if mono else ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
        return ImageFont.truetype(str(FONT_DIR / name), size * self.s)

    def p(self, value: int | float) -> int:
        return int(round(value * self.s))

    def box(self, xy: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return tuple(self.p(v) for v in xy)

    def color(self, name: str, alpha: int = 255) -> tuple[int, int, int, int]:
        r, g, b = PALETTE[name]
        return (r, g, b, alpha)

    def _background(self) -> None:
        w, h = self.img.size
        pix = self.img.load()
        for y in range(h):
            for x in range(w):
                nx = x / max(w - 1, 1)
                ny = y / max(h - 1, 1)
                v = int(22 * (1 - ny) + 10 * nx)
                pix[x, y] = (3 + v // 5, 8 + v // 4, 18 + v)
        overlay = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay, "RGBA")
        for cx, cy, radius, color in [
            (0.17, 0.18, 250, (120, 53, 255, 32)),
            (0.78, 0.18, 230, (255, 178, 55, 26)),
            (0.56, 0.70, 260, (24, 212, 220, 22)),
        ]:
            r = self.p(radius)
            x = self.p(cx * self.w)
            y = self.p(cy * self.h)
            od.ellipse((x - r, y - r, x + r, y + r), fill=color)
        overlay = overlay.filter(ImageFilter.GaussianBlur(self.p(42)))
        self.img = Image.alpha_composite(self.img.convert("RGBA"), overlay).convert("RGB")
        self.draw = ImageDraw.Draw(self.img, "RGBA")
        for x in range(0, self.w, 42):
            self.draw.line((self.p(x), 0, self.p(x), self.p(self.h)), fill=(80, 130, 220, 13), width=self.p(1))
        for y in range(0, self.h, 42):
            self.draw.line((0, self.p(y), self.p(self.w), self.p(y)), fill=(80, 130, 220, 10), width=self.p(1))

    def rounded(self, xy: tuple[int, int, int, int], color: str, *, radius: int = 14, fill_alpha: int = 28, width: int = 2) -> None:
        box = self.box(xy)
        rgba = self.color(color)
        glow = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow, "RGBA")
        for i, alpha in [(9, 26), (5, 42), (2, 70)]:
            gd.rounded_rectangle(
                tuple(v + (self.p(-i) if idx < 2 else self.p(i)) for idx, v in enumerate(box)),
                radius=self.p(radius + i),
                outline=rgba[:3] + (alpha,),
                width=self.p(width),
            )
        glow = glow.filter(ImageFilter.GaussianBlur(self.p(2)))
        self.img = Image.alpha_composite(self.img.convert("RGBA"), glow).convert("RGB")
        self.draw = ImageDraw.Draw(self.img, "RGBA")
        self.draw.rounded_rectangle(box, radius=self.p(radius), fill=rgba[:3] + (fill_alpha,), outline=rgba[:3] + (235,), width=self.p(width))

    def text(self, xy: tuple[int, int], text: str, *, size: int = 16, color: str = "text", bold: bool = False, mono: bool = False, anchor: str | None = None) -> None:
        self.draw.text((self.p(xy[0]), self.p(xy[1])), text, font=self.font(size, bold=bold, mono=mono), fill=self.color(color), anchor=anchor)

    def section(self, xy: tuple[int, int, int, int], title: str, color: str) -> None:
        self.rounded(xy, color, radius=16, fill_alpha=16, width=2)
        self.text(((xy[0] + xy[2]) // 2, xy[1] + 12), title, size=18, color=color, bold=True, anchor="ma")

    def card(self, card: Card) -> None:
        x1, y1, x2, y2 = card.xy
        h = y2 - y1
        title_size = min(card.title_size, 16 if h <= 62 else card.title_size)
        body_size = min(card.body_size, 12 if h <= 62 else card.body_size)
        self.rounded(card.xy, card.color, radius=10, fill_alpha=34, width=2)
        tx = x1 + 22
        if card.icon:
            icon_size = 24 if h <= 62 else 30
            self.text((x1 + 38, y1 + h // 2), card.icon, size=icon_size, color=card.color, bold=True, anchor="mm")
            tx = x1 + 72
        self.text((tx, y1 + 14), card.title, size=title_size, color=card.color, bold=True, mono=True)
        y = y1 + (38 if h <= 62 else 42)
        for line in card.lines:
            self.text((tx, y), line, size=body_size, color="text", mono=True)
            y += body_size + 6

    def line(self, points: Iterable[tuple[int, int]], color: str, *, arrow: bool = True, dashed: bool = False, width: int = 2) -> None:
        pts = [(self.p(x), self.p(y)) for x, y in points]
        rgba = self.color(color)
        if len(pts) < 2:
            return
        if dashed:
            for a, b in zip(pts, pts[1:]):
                self._dash(a, b, rgba, width)
        else:
            for glow_w, alpha in [(width + 7, 30), (width + 3, 60), (width, 230)]:
                self.draw.line(pts, fill=rgba[:3] + (alpha,), width=self.p(glow_w), joint="curve")
        if arrow:
            self._arrow(pts[-2], pts[-1], rgba)

    def _dash(self, a: tuple[int, int], b: tuple[int, int], color: tuple[int, int, int, int], width: int) -> None:
        ax, ay = a
        bx, by = b
        dist = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        if dist == 0:
            return
        dash = self.p(12)
        gap = self.p(9)
        steps = int(dist // (dash + gap)) + 1
        for i in range(steps):
            start = i * (dash + gap)
            end = min(start + dash, dist)
            if start >= dist:
                break
            t1, t2 = start / dist, end / dist
            p1 = (int(ax + (bx - ax) * t1), int(ay + (by - ay) * t1))
            p2 = (int(ax + (bx - ax) * t2), int(ay + (by - ay) * t2))
            self.draw.line((p1, p2), fill=color[:3] + (220,), width=self.p(width))

    def _arrow(self, a: tuple[int, int], b: tuple[int, int], color: tuple[int, int, int, int]) -> None:
        ang = atan2(b[1] - a[1], b[0] - a[0])
        length = self.p(11)
        spread = 0.55
        pts = [
            b,
            (int(b[0] - length * cos(ang - spread)), int(b[1] - length * sin(ang - spread))),
            (int(b[0] - length * cos(ang + spread)), int(b[1] - length * sin(ang + spread))),
        ]
        self.draw.polygon(pts, fill=color[:3] + (235,))

    def save(self, path: Path) -> None:
        self.img = self.img.resize((self.w, self.h), Image.Resampling.LANCZOS)
        self.img.save(path, optimize=True)


def generate_macro() -> None:
    c = NeonCanvas(1672, 660)
    c.section((230, 18, 1442, 120), "AI AGENTS", "purple")
    cards = [
        Card((270, 48, 480, 106), "purple", "Claude / Kilo", ("Claude Code",), ">_"),
        Card((525, 48, 735, 106), "blue", "Codex CLI", ("OpenAI Codex",), "</>"),
        Card((780, 48, 1010, 106), "cyan", "Cursor / Aider", ("IDE agents",), "A"),
        Card((1080, 48, 1365, 106), "yellow", "Gemini / OpenClaw", ("Copilot / ZooCode",), "[]"),
    ]
    for card in cards:
        c.card(card)

    c.card(Card((170, 145, 700, 230), "green", "SINAPSE-MCP.PY", ("MCP · CLI · REST API :37702",), "X"))
    c.card(Card((950, 145, 1450, 230), "yellow", "SINAPSE-MEMORY.PY", ("Plugin Hermes/Thoth",), "{}"))

    c.section((160, 250, 1512, 340), "UNIFIED MEMORY CORE (UMC) — HIVE_MIND.DB", "blue")
    c.text((836, 300), "graph · logs · vectors · FTS5 · vision · secrets", size=14, color="muted", mono=True, anchor="mm")

    c.text((836, 358), "KNOWLEDGE PIPELINE · K0-K10 · BORN-LARGE", size=15, color="cyan", bold=True, mono=True, anchor="ma")
    pipe = [
        Card((100, 385, 305, 440), "cyan", "Intake", (), "i"),
        Card((335, 385, 555, 440), "cyan", "Promotion", (), "p"),
        Card((585, 385, 890, 440), "cyan", "Index · 7 collections", (), "db"),
        Card((920, 385, 1195, 440), "cyan", "Retrieval Router", (), "r"),
        Card((1225, 385, 1540, 440), "cyan", "Answer + Citation", (), "ok"),
    ]
    for card in pipe:
        c.card(card)
    for a, b in zip(pipe, pipe[1:]):
        c.line([(a.xy[2], 412), (b.xy[0], 412)], "cyan")

    c.text((836, 468), "FEDERATED ORGANS", size=14, color="muted", bold=True, mono=True, anchor="ma")
    organs = [
        Card((70, 495, 300, 555), "purple", "claude-mem", ("temporal hippocampus",), "o"),
        Card((330, 495, 560, 555), "purple", "Graphify", ("structural graph",), "*"),
        Card((590, 495, 820, 555), "purple", "Graphiti", ("causal / temporal",), "t"),
        Card((850, 495, 1080, 555), "green", "sqlite-vec / Milvus", ("VectorBackend (K2)",), "db"),
        Card((1110, 495, 1340, 555), "purple", "LightRAG", ("multi-hop",), "g"),
    ]
    for card in organs:
        c.card(card)
    adapters = [
        Card((70, 575, 480, 630), "yellow", "RAGFlow — doc adapter (K6)", (), "!"),
        Card((510, 575, 920, 630), "yellow", "LlamaIndex — rerank adapter (K7)", (), "!"),
    ]
    for card in adapters:
        c.rounded(card.xy, card.color, radius=10, fill_alpha=18, width=2)
        c.card(Card(card.xy, card.color, card.title, card.lines, card.icon, title_size=14))

    c.line([(475, 106), (475, 145)], "purple")
    c.line([(1200, 106), (1200, 145)], "yellow")
    c.line([(435, 230), (435, 250)], "green")
    c.line([(1200, 230), (1200, 250)], "yellow")
    c.line([(836, 340), (836, 355)], "blue")
    c.line([(836, 440), (836, 460)], "cyan")
    c.save(OUT / "architecture-diagram.png")


def generate_complete() -> None:
    c = NeonCanvas(1536, 1220)
    c.text((768, 28), "HIVE-MIND — KNOWLEDGE PROMOTION ARCHITECTURE (K0-K10)", size=24, color="text", bold=True, mono=True, anchor="ma")
    c.text((768, 62), "docs/11-knowledge-promotion-architecture.md · canonical pipeline, born-large by contract", size=13, color="muted", mono=True, anchor="ma")

    steps = [
        ("[1] Capture Layer", "hooks, MCP, CLI, browser, documents, code, screenshots, runtime", "purple", "1"),
        ("[2] K4 Temporal Hippocampus — claude-mem", "user_prompts, observations, discoveries, session_summaries", "blue", "2"),
        ("[3] K3 Knowledge Intake", "normalizes, classifies, deduplicates, preserves evidence", "cyan", "3"),
        ("[4] K3 Promotion Layer", "raw -> fact / decision / learning / preference / task / rationale", "cyan", "4"),
        ("[5] Anatomical Memory — cerebro/ + UMC", "cortex temporal/frontal/parietal/occipital/insula · cerebelo · diencefalo · tronco", "blue", "*"),
        ("[6] K2 Index Layer", "FTS5, sqlite-vec / Milvus (VectorBackend), Graphify, Graphiti, LightRAG", "green", "6"),
        ("[7] K7 Retrieval Router", "routes by intent: temporal, memory, document, code, graph, causal, hybrid", "purple", "7"),
        ("[8] Answer + Citation", "response with source, evidence, retrieval_path and confidence", "yellow", "8"),
        ("[9] Feedback", "new observation, decision, learning or task", "red", "9"),
    ]
    x1, x2 = 40, 800
    y = 100
    step_h = 92
    gap = 24
    step_boxes = []
    for title, line, color, icon in steps:
        box = (x1, y, x2, y + step_h)
        step_boxes.append(box)
        c.card(Card(box, color, title, (line,), icon, title_size=15, body_size=12))
        y += step_h + gap

    for a, b in zip(step_boxes, step_boxes[1:]):
        mid_x = (x1 + x2) // 2
        c.line([(mid_x, a[3]), (mid_x, b[1])], "muted", width=2)

    loop_x = x2 + 34
    c.line(
        [(x2, step_boxes[-1][1] + step_h // 2), (loop_x, step_boxes[-1][1] + step_h // 2),
         (loop_x, step_boxes[0][1] + step_h // 2), (x2, step_boxes[0][1] + step_h // 2)],
        "cyan", dashed=True, arrow=True,
    )
    c.text((loop_x + 14, (step_boxes[0][1] + step_boxes[-1][1]) // 2), "feedback", size=12, color="cyan", mono=True, anchor="mm")

    side_x1, side_x2 = 850, 1500
    side_cards = [
        ("VectorBackend", "K2", ("upsert · delete · query · hybrid_query · count · health", "7 canonical collections: memory/observation/document/code/visual/graph/summary"), "green"),
        ("DocumentPipeline", "K6", ("document_memories (parent) -> document_chunks -> document_vectors", "auditable citations: source_uri, offsets, score, parent"), "blue"),
        ("RAGFlow — headless adapter", "K6", ("parsing / chunking / citation extraction only", "never source of truth — output normalized into UMC"), "yellow"),
        ("RetrievalRouter", "K7", ("core/retrieval/router.py", "always returns retrieval_path, citations, confidence, missing_context"), "purple"),
        ("LlamaIndex — rerank adapter", "K7", ("optional HIVE_RETRIEVAL_RERANKER, fail-open", "never decides routing"), "yellow"),
        ("Knowledge Health", "K8", ("coverage metrics per collection", "orphan-vector pruning with auditable tombstones"), "cyan"),
    ]
    sy = 100
    scard_h = 148
    sgap = 20
    for title, badge, (l1, l2), color in side_cards:
        box = (side_x1, sy, side_x2, sy + scard_h)
        adapter = "adapter" in title.lower()
        c.rounded(box, color, radius=10, fill_alpha=20 if adapter else 30, width=2)
        c.text((side_x1 + 22, sy + 14), title, size=14, color=color, bold=True, mono=True)
        c.text((side_x2 - 16, sy + 16), badge, size=11, color=color, bold=True, mono=True, anchor="ra")
        c.text((side_x1 + 22, sy + 46), l1, size=12, color="text", mono=True)
        c.text((side_x1 + 22, sy + 46 + 22), l2, size=12, color="muted", mono=True)
        sy += scard_h + sgap

    c.text((768, 1178), "● local-first     ● born-large     ● plugable by contract     ● anatomical source of truth     ● auditable by evidence", size=13, color="muted", bold=True, mono=True, anchor="ma")
    c.save(OUT / "architecture-diagram-complet.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    generate_macro()
    generate_complete()


if __name__ == "__main__":
    main()
