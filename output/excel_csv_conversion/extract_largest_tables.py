from __future__ import annotations

import csv
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL_RE = re.compile(r"^([A-Z]+)([0-9]+)$")


def col_number(letters: str) -> int:
    result = 0
    for char in letters:
        result = result * 26 + ord(char) - 64
    return result


def cell_position(reference: str) -> tuple[int, int]:
    match = CELL_RE.match(reference)
    if not match:
        raise ValueError(f"Unsupported cell reference: {reference}")
    return int(match.group(2)), col_number(match.group(1))


def xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext())


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [xml_text(item) for item in root.findall(f"{{{NS_MAIN}}}si")]


def workbook_sheets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{{{NS_PKG_REL}}}Relationship")
    }
    sheets = []
    for sheet in workbook.find(f"{{{NS_MAIN}}}sheets"):
        rel_id = sheet.attrib[f"{{{NS_REL}}}id"]
        target = targets[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        sheets.append((sheet.attrib["name"], target))
    return sheets


def parse_sheet(
    archive: zipfile.ZipFile, sheet_path: str, strings: list[str]
) -> dict[tuple[int, int], str]:
    root = ET.fromstring(archive.read(sheet_path))
    cells: dict[tuple[int, int], str] = {}
    for cell in root.findall(f".//{{{NS_MAIN}}}c"):
        position = cell_position(cell.attrib["r"])
        cell_type = cell.attrib.get("t", "n")
        value_node = cell.find(f"{{{NS_MAIN}}}v")
        if cell_type == "inlineStr":
            value = xml_text(cell.find(f"{{{NS_MAIN}}}is"))
        elif value_node is None:
            value = ""
        elif cell_type == "s":
            value = strings[int(value_node.text or "0")]
        elif cell_type == "b":
            value = "TRUE" if value_node.text == "1" else "FALSE"
        else:
            value = value_node.text or ""
        if value != "":
            cells[position] = value
    return cells


def row_blocks(cells: dict[tuple[int, int], str]) -> list[dict[str, int]]:
    populated_rows = sorted({row for row, _ in cells})
    blocks: list[list[int]] = []
    for row in populated_rows:
        if not blocks or row > blocks[-1][-1] + 1:
            blocks.append([row])
        else:
            blocks[-1].append(row)

    result = []
    for rows in blocks:
        block_cells = [(r, c) for (r, c) in cells if rows[0] <= r <= rows[-1]]
        min_col = min(c for _, c in block_cells)
        max_col = max(c for _, c in block_cells)
        result.append(
            {
                "min_row": rows[0],
                "max_row": rows[-1],
                "min_col": min_col,
                "max_col": max_col,
                "rows": rows[-1] - rows[0] + 1,
                "cols": max_col - min_col + 1,
                "area": (rows[-1] - rows[0] + 1) * (max_col - min_col + 1),
                "nonempty": len(block_cells),
            }
        )
    return result


def write_csv(
    destination: Path,
    cells: dict[tuple[int, int], str],
    block: dict[str, int],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        for row in range(block["min_row"], block["max_row"] + 1):
            writer.writerow(
                [
                    cells.get((row, col), "")
                    for col in range(block["min_col"], block["max_col"] + 1)
                ]
            )


def process(source: Path, destination: Path) -> dict[str, object]:
    with zipfile.ZipFile(source) as archive:
        strings = shared_strings(archive)
        candidates = []
        parsed = {}
        for sheet_name, sheet_path in workbook_sheets(archive):
            cells = parse_sheet(archive, sheet_path, strings)
            parsed[sheet_name] = cells
            for block in row_blocks(cells):
                candidates.append({"sheet": sheet_name, **block})

    if not candidates:
        raise ValueError(f"No non-empty tables found in {source}")

    # Primary criterion: rectangular table area. Non-empty cell count breaks ties.
    largest = max(candidates, key=lambda item: (item["area"], item["nonempty"]))
    write_csv(destination, parsed[str(largest["sheet"])], largest)
    return {
        "source": str(source),
        "destination": str(destination),
        "selected": largest,
        "all_candidates": candidates,
    }


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit(
            "Usage: extract_largest_tables.py SOURCE1 DEST1 SOURCE2 DEST2"
        )
    reports = [
        process(Path(sys.argv[1]), Path(sys.argv[2])),
        process(Path(sys.argv[3]), Path(sys.argv[4])),
    ]
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
