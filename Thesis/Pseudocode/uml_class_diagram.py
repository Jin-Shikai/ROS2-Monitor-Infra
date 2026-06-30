"""Generate a clean conceptual UML class diagram for the pseudocode chapter."""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BUNDLED_PYTHON = Path(
    "C:/Users/Probe/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/python.exe"
)


def running_on_bundled_python() -> bool:
    try:
        return Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve()
    except OSError:
        return False


if sys.version_info < (3, 9) and BUNDLED_PYTHON.exists() and not running_on_bundled_python():
    subprocess.run([str(BUNDLED_PYTHON), __file__], check=True)
    sys.exit(0)

try:
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
except ModuleNotFoundError:
    if BUNDLED_PYTHON.exists() and not running_on_bundled_python():
        subprocess.run([str(BUNDLED_PYTHON), __file__], check=True)
        sys.exit(0)
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas


OUT_DIR = Path(__file__).resolve().parent
PDF_PATH = OUT_DIR / "uml_class_diagram.pdf"
PNG_PATH = OUT_DIR / "uml_class_diagram.png"

PAGE_W = 1460
PAGE_H = 820
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
INK = colors.HexColor("#222222")
LIGHT = colors.HexColor("#f7f7f7")


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> tuple[float, float]:
        return self.x, self.y + self.h / 2

    @property
    def right(self) -> tuple[float, float]:
        return self.x + self.w, self.y + self.h / 2

    @property
    def top(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h

    @property
    def bottom(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y

    def point(self, side: str, offset: float = 0) -> tuple[float, float]:
        if side == "left":
            return self.x, self.y + self.h / 2 + offset
        if side == "right":
            return self.x + self.w, self.y + self.h / 2 + offset
        if side == "top":
            return self.x + self.w / 2 + offset, self.y + self.h
        if side == "bottom":
            return self.x + self.w / 2 + offset, self.y
        raise ValueError(side)


def register_fonts() -> None:
    global FONT_REGULAR, FONT_BOLD
    font_dir = Path("C:/Windows/Fonts")
    regular = font_dir / "arial.ttf"
    bold = font_dir / "arialbd.ttf"
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("ArialEmbedded", str(regular)))
        pdfmetrics.registerFont(TTFont("ArialEmbedded-Bold", str(bold)))
        FONT_REGULAR = "ArialEmbedded"
        FONT_BOLD = "ArialEmbedded-Bold"


def text_width(text: str, size: int, bold: bool = False) -> float:
    return pdfmetrics.stringWidth(text, FONT_BOLD if bold else FONT_REGULAR, size)


def draw_text(c: canvas.Canvas, text: str, x: float, y: float, size: int = 10, bold: bool = False) -> None:
    c.setFillColor(INK)
    c.setFont(FONT_BOLD if bold else FONT_REGULAR, size)
    c.drawString(x, y, text)


def draw_centered(c: canvas.Canvas, text: str, x: float, y: float, size: int = 10, bold: bool = False) -> None:
    c.setFillColor(INK)
    c.setFont(FONT_BOLD if bold else FONT_REGULAR, size)
    c.drawCentredString(x, y, text)


def draw_label(c: canvas.Canvas, text: str, x: float, y: float, size: int = 9) -> None:
    pad_x = 4
    pad_y = 2
    w = text_width(text, size) + pad_x * 2
    c.setFillColor(colors.white)
    c.rect(x - w / 2, y - pad_y, w, size + pad_y, stroke=0, fill=1)
    draw_centered(c, text, x, y, size)


def draw_class_box(
    c: canvas.Canvas,
    box: Box,
    name: str,
    *,
    stereotype: str | None = None,
    attributes: list[str] | None = None,
    operations: list[str] | None = None,
) -> None:
    attributes = attributes or []
    operations = operations or []
    header_h = 42 if stereotype else 34
    op_h = 0 if not operations else 26 + 13 * (len(operations) - 1)
    attr_h = box.h - header_h - op_h
    if attr_h < 24:
        raise ValueError(f"Box for {name} is too short")

    c.setLineWidth(1.2)
    c.setStrokeColor(INK)
    c.setFillColor(colors.white)
    c.rect(box.x, box.y, box.w, box.h, stroke=1, fill=1)
    c.setFillColor(LIGHT)
    c.rect(box.x, box.y + box.h - header_h, box.w, header_h, stroke=0, fill=1)
    c.setStrokeColor(INK)
    c.line(box.x, box.y + box.h - header_h, box.x + box.w, box.y + box.h - header_h)
    if operations:
        c.line(box.x, box.y + op_h, box.x + box.w, box.y + op_h)

    if stereotype:
        draw_centered(c, f"<<{stereotype}>>", box.x + box.w / 2, box.y + box.h - 16, 9)
        draw_centered(c, name, box.x + box.w / 2, box.y + box.h - 33, 15, bold=True)
    else:
        draw_centered(c, name, box.x + box.w / 2, box.y + box.h - 22, 15, bold=True)

    y = box.y + box.h - header_h - 17
    for item in attributes:
        draw_text(c, item, box.x + 12, y, 10)
        y -= 15

    y = box.y + op_h - 17
    for item in operations:
        draw_text(c, item, box.x + 12, y, 10)
        y -= 15


def direction_angle(direction: str) -> float:
    return {
        "right": 0,
        "up": math.pi / 2,
        "left": math.pi,
        "down": -math.pi / 2,
    }[direction]


def draw_polyline(c: canvas.Canvas, points: list[tuple[float, float]], *, dashed: bool = False) -> None:
    c.setStrokeColor(INK)
    c.setLineWidth(1.2)
    c.setDash(5, 5) if dashed else c.setDash()
    path = c.beginPath()
    path.moveTo(points[0][0], points[0][1])
    for x, y in points[1:]:
        path.lineTo(x, y)
    c.drawPath(path, stroke=1, fill=0)
    c.setDash()


def draw_open_vee(c: canvas.Canvas, tip: tuple[float, float], direction: str, size: float = 10) -> None:
    angle = direction_angle(direction)
    left = (
        tip[0] - size * math.cos(angle - math.pi / 6),
        tip[1] - size * math.sin(angle - math.pi / 6),
    )
    right = (
        tip[0] - size * math.cos(angle + math.pi / 6),
        tip[1] - size * math.sin(angle + math.pi / 6),
    )
    draw_polyline(c, [left, tip, right])


def draw_open_triangle(c: canvas.Canvas, tip: tuple[float, float], direction: str, size: float = 15) -> None:
    angle = direction_angle(direction)
    left = (
        tip[0] - size * math.cos(angle - math.pi / 7),
        tip[1] - size * math.sin(angle - math.pi / 7),
    )
    right = (
        tip[0] - size * math.cos(angle + math.pi / 7),
        tip[1] - size * math.sin(angle + math.pi / 7),
    )
    c.setFillColor(colors.white)
    c.setStrokeColor(INK)
    path = c.beginPath()
    path.moveTo(tip[0], tip[1])
    path.lineTo(left[0], left[1])
    path.lineTo(right[0], right[1])
    path.close()
    c.drawPath(path, stroke=1, fill=1)


def draw_composition_diamond(c: canvas.Canvas, tip: tuple[float, float], direction: str, size: float = 11) -> None:
    angle = direction_angle(direction)
    p0 = tip
    p1 = (
        tip[0] + size * math.cos(angle - math.pi / 3),
        tip[1] + size * math.sin(angle - math.pi / 3),
    )
    p2 = (
        tip[0] + size * 1.8 * math.cos(angle),
        tip[1] + size * 1.8 * math.sin(angle),
    )
    p3 = (
        tip[0] + size * math.cos(angle + math.pi / 3),
        tip[1] + size * math.sin(angle + math.pi / 3),
    )
    c.setFillColor(INK)
    c.setStrokeColor(INK)
    path = c.beginPath()
    path.moveTo(p0[0], p0[1])
    for p in (p1, p2, p3):
        path.lineTo(p[0], p[1])
    path.close()
    c.drawPath(path, stroke=1, fill=1)


def association(
    c: canvas.Canvas,
    points: list[tuple[float, float]],
    *,
    label: str | None = None,
    label_at: tuple[float, float] | None = None,
    composition_at_start: str | None = None,
) -> None:
    draw_polyline(c, points)
    if composition_at_start:
        draw_composition_diamond(c, points[0], composition_at_start)
    if label and label_at:
        draw_label(c, label, label_at[0], label_at[1])


def dependency(
    c: canvas.Canvas,
    points: list[tuple[float, float]],
    *,
    end_direction: str,
    label: str | None = None,
    label_at: tuple[float, float] | None = None,
) -> None:
    draw_polyline(c, points, dashed=True)
    draw_open_vee(c, points[-1], end_direction)
    if label and label_at:
        draw_label(c, label, label_at[0], label_at[1])


def inheritance(c: canvas.Canvas, child: tuple[float, float], parent: tuple[float, float], via_y: float) -> None:
    points = [child, (child[0], via_y), (parent[0], via_y), parent]
    draw_polyline(c, points)
    draw_open_triangle(c, parent, "up")


def render_png() -> None:
    candidates = [
        "C:/Users/Probe/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe",
        shutil.which("pdftoppm"),
    ]
    pdftoppm = next((p for p in candidates if p and Path(p).exists() and Path(p).suffix.lower() == ".exe"), None)
    if pdftoppm is None:
        return
    prefix = OUT_DIR / "uml_class_diagram"
    subprocess.run([pdftoppm, "-png", "-singlefile", "-r", "150", str(PDF_PATH), str(prefix)], check=True)


def main() -> None:
    register_fonts()
    c = canvas.Canvas(str(PDF_PATH), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("Host Runtime Link JSON UML Class Diagram")
    c.setAuthor("ROS2-Monitor-Infra")

    draw_centered(c, "UML Class Diagram for Host Runtime Link JSON", PAGE_W / 2, PAGE_H - 34, 16, bold=True)

    request = Box(570, 660, 320, 85)
    host = Box(85, 515, 230, 95)
    link = Box(1120, 455, 250, 155)
    runtime = Box(520, 500, 250, 110)
    transport = Box(1120, 250, 250, 85)
    transport_kind = Box(1160, 80, 170, 95)

    ros2 = Box(70, 305, 220, 85)
    monitor = Box(330, 290, 220, 100)
    converter = Box(590, 260, 230, 130)
    verdict_service = Box(855, 260, 230, 130)

    source = Box(70, 60, 220, 150)
    source_kind = Box(320, 80, 160, 110)
    data_filter = Box(560, 75, 190, 80)
    dsl_converter = Box(790, 75, 190, 80)

    draw_class_box(c, request, "GenerationRequest",
                   attributes=["+ hosts", "+ links"])
    draw_class_box(c, host, "Host",
                   attributes=["+ id"])
    draw_class_box(c, link, "Link",
                   attributes=["+ id", "+ from_host", "+ to_host", "+ from_runtime", "+ to_runtime", "+ payload", "+ transport"])
    draw_class_box(c, runtime, "Runtime", stereotype="abstract",
                   attributes=["+ id", "+ kind"])
    draw_class_box(c, transport, "Transport",
                   attributes=["+ kind"])
    draw_class_box(c, transport_kind, "TransportKind",
                   attributes=["mqtt", "file"])

    draw_class_box(c, ros2, "ROS2",
                   attributes=["+ sources"])
    draw_class_box(c, monitor, "Monitor",
                   attributes=["+ subscribe"])
    draw_class_box(c, converter, "Converter",
                   attributes=["+ converter", "+ class_path", "+ input_from", "+ output_to"])
    draw_class_box(c, verdict_service, "VerdictService",
                   attributes=["+ class_path", "+ input_from", "+ output_to"])
    draw_class_box(c, source, "Source",
                   attributes=["+ id", "+ source_kind", "+ name", "+ interface"])
    draw_class_box(c, source_kind, "SourceKind",
                   attributes=["topic", "service", "action"])
    draw_class_box(c, data_filter, "DataFilter",
                   attributes=["+ converter: data_filter"])
    draw_class_box(c, dsl_converter, "DslConverter",
                   attributes=["+ converter: dsl_converter"])

    top_y = 635
    request_hosts = request.point("bottom", -80)
    request_links = request.point("bottom", 80)
    association(c, [request_hosts, (request_hosts[0], top_y), (host.top[0], top_y), host.top],
                label="hosts", label_at=(325, top_y + 11), composition_at_start="down")
    association(c, [request_links, (request_links[0], top_y), (link.top[0], top_y), link.top],
                label="links", label_at=(1085, top_y + 11), composition_at_start="down")
    draw_text(c, "0..*", host.top[0] + 10, host.y + host.h + 6, 9)
    draw_text(c, "0..*", link.top[0] + 10, link.y + link.h + 6, 9)

    association(c, [host.right, runtime.point("left", 7.5)],
                label="runtimes", label_at=(420, 565), composition_at_start="right")
    draw_text(c, "1", host.x + host.w + 10, host.y + host.h / 2 + 12, 9)
    draw_text(c, "0..*", runtime.x - 34, runtime.y + runtime.h / 2 + 12, 9)

    association(c, [link.bottom, transport.top],
                composition_at_start="down")
    association(c, [transport.bottom, transport_kind.top])
    parent = runtime.bottom
    inheritance(c, ros2.top, parent, 440)
    inheritance(c, monitor.top, parent, 440)
    inheritance(c, converter.top, parent, 440)
    inheritance(c, verdict_service.top, parent, 440)

    association(c, [ros2.bottom, source.top],
                composition_at_start="down")
    association(c, [source.right, source_kind.left])

    inheritance(c, data_filter.top, converter.bottom, 235)
    inheritance(c, dsl_converter.top, converter.bottom, 235)

    c.showPage()
    c.save()
    render_png()
    print(PDF_PATH)
    print(PNG_PATH)


if __name__ == "__main__":
    main()
