from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import Zone


def group_name_for_zone(zone: Zone) -> str:
    if zone.layer_name:
        return zone.layer_name
    return f"Velocity {zone.vel_sample}"


def indent_xml(elem: ET.Element, level: int = 0) -> None:
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = i


def make_multisample_xml(
    *,
    name: str,
    creator: str,
    description: str,
    category: str,
    keywords: list[str],
    zones: list[Zone],
    round_robin: bool,
) -> bytes:
    root = ET.Element("multisample", {"name": name})
    ET.SubElement(root, "generator").text = "ARP 2600 AutoSampler Python"
    ET.SubElement(root, "category").text = category
    ET.SubElement(root, "creator").text = creator
    if description:
        ET.SubElement(root, "description").text = description
    if keywords:
        keywords_el = ET.SubElement(root, "keywords")
        for keyword in keywords:
            ET.SubElement(keywords_el, "keyword").text = keyword

    groups: list[str] = []
    for zone in zones:
        group_name = group_name_for_zone(zone)
        if group_name not in groups:
            groups.append(group_name)

    group_index = {group_name: index for index, group_name in enumerate(groups)}
    for group_name in groups:
        ET.SubElement(root, "group", {"name": group_name})

    for zone in zones:
        attrs = {
            "file": f"Samples/{zone.filename}",
            "sample-start": "0",
            "sample-stop": str(zone.frames),
            "gain": "0.000",
            "group": str(group_index[group_name_for_zone(zone)]),
        }
        if round_robin:
            attrs["zone-logic"] = "round-robin"
        sample_el = ET.SubElement(root, "sample", attrs)
        ET.SubElement(
            sample_el,
            "key",
            {
                "root": str(zone.root),
                "low": str(zone.key_low),
                "high": str(zone.key_high),
                "track": "1.0",
                "tune": "0.0",
            },
        )
        ET.SubElement(sample_el, "velocity", {"low": str(zone.vel_low), "high": str(zone.vel_high)})
        ET.SubElement(sample_el, "select", {"low": "1", "high": "127"})

    indent_xml(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def package_multisample(folder: Path, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()
    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.write(folder / "multisample.xml", "multisample.xml")
        samples_dir = folder / "Samples"
        for wav in sorted(samples_dir.glob("*.wav")):
            zf.write(wav, f"Samples/{wav.name}")
