"""Generate the editable draw.io version of the UML class diagram."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


OUT_PATH = Path(__file__).with_name("uml_class_diagram.drawio")

PAGE_W = 1460
PAGE_H = 820


@dataclass(frozen=True)
class Box:
    id: str
    name: str
    x: float
    y: float
    w: float
    h: float
    attributes: tuple[str, ...] = ()
    stereotype: str | None = None

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def mx(parent_node: ET.Element, tag: str, **attrs: object) -> ET.Element:
    node = ET.SubElement(parent_node, tag)
    for key, value in attrs.items():
        if value is not None:
            node.set(key, str(value))
    return node


def class_value(box: Box) -> str:
    title = box.name if box.stereotype is None else f"&lt;&lt;{box.stereotype}&gt;&gt;<br><b>{box.name}</b>"
    attrs = "<br>".join(html.escape(a) for a in box.attributes)
    return (
        f"<table style=\"width:100%;height:100%;border-collapse:collapse;\">"
        f"<tr><td style=\"height:32px;text-align:center;font-weight:bold;background-color:#f7f7f7;\">{title}</td></tr>"
        f"<tr><td style=\"border-top:1px solid #222222;text-align:left;vertical-align:top;padding:8px 10px;\">{attrs}</td></tr>"
        f"</table>"
    )


def add_class(root: ET.Element, box: Box) -> None:
    cell = mx(
        root,
        "mxCell",
        id=box.id,
        value=class_value(box),
        style=(
            "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#222222;"
            "fontFamily=Arial;fontSize=12;align=center;verticalAlign=middle;"
        ),
        vertex="1",
        parent="1",
    )
    mx(cell, "mxGeometry", x=box.x, y=box.y, width=box.w, height=box.h, as_="geometry")
    cell.find("mxGeometry").set("as", "geometry")
    cell.find("mxGeometry").attrib.pop("as_", None)


def add_text(root: ET.Element, cid: str, text: str, x: float, y: float, w: float = 48, h: float = 20) -> None:
    cell = mx(
        root,
        "mxCell",
        id=cid,
        value=html.escape(text),
        style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontFamily=Arial;fontSize=12;",
        vertex="1",
        parent="1",
    )
    geom = mx(cell, "mxGeometry", x=x, y=y, width=w, height=h)
    geom.set("as", "geometry")


def add_edge(
    root: ET.Element,
    cid: str,
    source: str,
    target: str,
    *,
    label: str = "",
    style: str = "",
    points: list[tuple[float, float]] | None = None,
) -> None:
    edge_style = (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;"
        "html=1;strokeColor=#222222;fontFamily=Arial;fontSize=12;"
    ) + style
    cell = mx(
        root,
        "mxCell",
        id=cid,
        value=html.escape(label),
        style=edge_style,
        edge="1",
        parent="1",
        source=source,
        target=target,
    )
    geom = mx(cell, "mxGeometry", relative="1")
    geom.set("as", "geometry")
    if points:
        arr = mx(geom, "Array")
        arr.set("as", "points")
        for x, y in points:
            mx(arr, "mxPoint", x=x, y=y)


def build() -> ET.ElementTree:
    mxfile = ET.Element(
        "mxfile",
        host="app.diagrams.net",
        modified="2026-06-30T00:00:00.000Z",
        agent="Codex",
        version="26.0.0",
        type="device",
    )
    diagram = mx(mxfile, "diagram", id="uml-class-diagram", name="Page-1")
    model = mx(
        diagram,
        "mxGraphModel",
        dx="1460",
        dy="820",
        grid="1",
        gridSize="10",
        guides="1",
        tooltips="1",
        connect="1",
        arrows="1",
        fold="1",
        page="1",
        pageScale="1",
        pageWidth=PAGE_W,
        pageHeight=PAGE_H,
        math="0",
        shadow="0",
    )
    root = mx(model, "root")
    mx(root, "mxCell", id="0")
    mx(root, "mxCell", id="1", parent="0")

    boxes = [
        Box("request", "GenerationRequest", 570, 55, 320, 85, ("+ hosts", "+ links")),
        Box("host", "Host", 85, 210, 230, 95, ("+ id",)),
        Box("link", "Link", 1120, 210, 250, 155, ("+ id", "+ from_host", "+ to_host", "+ from_runtime", "+ to_runtime", "+ payload", "+ transport")),
        Box("runtime", "Runtime", 520, 195, 250, 110, ("+ id", "+ kind"), "abstract"),
        Box("transport", "Transport", 1120, 485, 250, 85, ("+ kind",)),
        Box("transport_kind", "TransportKind", 1160, 645, 170, 95, ("mqtt", "file")),
        Box("ros2", "ROS2", 70, 365, 220, 85, ("+ sources",)),
        Box("monitor", "Monitor", 330, 380, 220, 100, ("+ subscribe",)),
        Box("converter", "Converter", 590, 380, 230, 130, ("+ converter", "+ class_path", "+ input_from", "+ output_to")),
        Box("verdict_service", "VerdictService", 855, 380, 230, 130, ("+ class_path", "+ input_from", "+ output_to")),
        Box("source", "Source", 70, 610, 220, 150, ("+ id", "+ source_kind", "+ name", "+ interface")),
        Box("source_kind", "SourceKind", 320, 635, 160, 110, ("topic", "service", "action")),
        Box("data_filter", "DataFilter", 560, 655, 190, 80, ("+ converter: data_filter",)),
        Box("dsl_converter", "DslConverter", 790, 655, 190, 80, ("+ converter: dsl_converter",)),
    ]

    add_text(root, "title", "UML Class Diagram for Host Runtime Link JSON", 480, 16, 500, 28)
    title = root.find("./mxCell[@id='title']")
    title.set("style", title.get("style") + "fontStyle=1;fontSize=16;")

    for box in boxes:
        add_class(root, box)

    composition = "startArrow=diamond;startFill=1;endArrow=none;"
    association = "endArrow=none;"
    generalization = "endArrow=block;endFill=0;"

    add_edge(root, "e_request_host", "request", "host", label="hosts", style=composition, points=[(650, 160), (200, 160)])
    add_edge(root, "e_request_link", "request", "link", label="links", style=composition, points=[(810, 160), (1245, 160)])
    add_text(root, "m_host_many", "0..*", 178, 178)
    add_text(root, "m_link_many", "0..*", 1245, 178)

    add_edge(root, "e_host_runtime", "host", "runtime", label="runtimes", style=composition)
    add_text(root, "m_host_one", "1", 315, 235, 30, 20)
    add_text(root, "m_runtime_many", "0..*", 485, 235, 45, 20)

    add_edge(root, "e_link_transport", "link", "transport", style=composition)
    add_edge(root, "e_transport_kind", "transport", "transport_kind", style=association)

    add_edge(root, "e_ros2_runtime", "ros2", "runtime", style=generalization, points=[(180, 335), (645, 335)])
    add_edge(root, "e_monitor_runtime", "monitor", "runtime", style=generalization, points=[(440, 335), (645, 335)])
    add_edge(root, "e_converter_runtime", "converter", "runtime", style=generalization, points=[(705, 335), (645, 335)])
    add_edge(root, "e_verdict_runtime", "verdict_service", "runtime", style=generalization, points=[(970, 335), (645, 335)])

    add_edge(root, "e_ros2_source", "ros2", "source", style=composition)
    add_edge(root, "e_source_kind", "source", "source_kind", style=association)

    add_edge(root, "e_datafilter_converter", "data_filter", "converter", style=generalization, points=[(655, 565), (705, 565)])
    add_edge(root, "e_dslconverter_converter", "dsl_converter", "converter", style=generalization, points=[(885, 565), (705, 565)])

    return ET.ElementTree(mxfile)


def main() -> None:
    tree = build()
    tree.write(OUT_PATH, encoding="utf-8", xml_declaration=True)
    print(OUT_PATH)


if __name__ == "__main__":
    main()
