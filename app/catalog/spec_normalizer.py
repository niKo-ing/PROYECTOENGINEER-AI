"""Normalize component spec values into structured JSON items.

The canonical Motherboard schema introduced ``data_type="json"`` keys whose
``item_schema`` describes a list of objects (M.2 slots, PCIe slots, connectors,
rear ports...).  A store spec sheet or an LLM often yields either a compact
"1x PCIe 5.0 x16, 2x PCIe 4.0 x1" form or a free text sentence.  This module
parses those raw strings into the canonical list-of-dicts shape so the spec
sheet can render arrays while the DB keeps a single raw + structured value.

Parsing is intentionally strict about *not inventing* data:
  * a generation / lane count / interface is only filled when the text states it;
  * unrecognizable or partially-known text degrades to a single item keeping the
    raw evidence string so nothing is silently dropped.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

import unicodedata

# Unit-normalization helpers shared with the rest of the pipeline.
_COUNT_RE = re.compile(r"^\s*(\d+)\s*(?:x|X|×|x:)?\s*")
_LANES_RE = re.compile(r"[xX×](\d{1,2})\b")
_GEN_DOT_RE = re.compile(r"(?:pcie|pci[\s-]express)[\s]*(\d+\.\d+)")
_GEN_WORD_RE = re.compile(r"\bgen(?:er(?:ation)?)?[\s]*(\d+)", re.IGNORECASE)


def nfkd(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized


def _split_items(raw_value: str, *, allow_plus: bool = False) -> list[str]:
    """Split a compact list phrase ('1x X, 2x Y; Z') into individual phrases."""
    text = nfkd(raw_value)
    text = re.sub(r"\s+", " ", text)
    separators = r"[;,]" if not allow_plus else r"[;,]"
    parts: list[str] = []
    for piece in re.split(separators, text):
        piece = piece.strip(" .")
        if piece:
            parts.append(piece)
    return parts or ([text.strip(" .")] if text.strip(" .") else [])


def _count(phrase: str, ignore_pin: bool = False) -> int:
    if ignore_pin:
        # Power connectors: a leading number may be a pin count ("24-pin") rather
        # than a multiplier. Only an explicit "Nx"/"N ×" denotes connector count.
        match = re.match(r"^\s*(\d+)\s*(?:x|X|×|x:|×:)", nfkd(phrase))
        return int(match.group(1)) if match else 1
    match = _COUNT_RE.match(phrase)
    return int(match.group(1)) if match else 1


def _lanes(phrase: str) -> int | None:
    match = _LANES_RE.search(phrase)
    return int(match.group(1)) if match else None


def _generation(phrase: str) -> str | None:
    dot = _GEN_DOT_RE.search(phrase)
    if dot:
        return dot.group(1)
    word = _GEN_WORD_RE.search(phrase)
    if word:
        return f"{word.group(1)}.0"
    return None


# --------------------------------------------------------------------------- #
# PCIe
# --------------------------------------------------------------------------- #
def _pcie_slot_label(phrase: str, generation: str | None, lanes: int | None) -> str | None:
    if "x16" in phrase and "x8" not in phrase:
        return "PCIe x16"
    if "x8" in phrase:
        return "PCIe x8"
    if "x4" in phrase and "x16" not in phrase:
        return "PCIe x4"
    if "x1" in phrase and "x16" not in phrase and "x8" not in phrase and "x4" not in phrase:
        return "PCIe x1"
    return None


def normalize_pcie_slots(raw_value: str) -> list[dict]:
    items: list[dict] = []
    for phrase in _split_items(raw_value):
        has_pcie = bool(re.search(r"pci(e)?[\s-]*express|pcie", phrase))
        if not has_pcie:
            items.append({"type": phrase.strip() or None, "generation": None, "lanes": None, "count": _count(phrase)})
            continue
        generation = _generation(phrase)
        lanes = _lanes(phrase)
        slot_type = _pcie_slot_label(phrase, generation, lanes)
        items.append(
            {
                "type": slot_type or "PCIe",
                "generation": generation,
                "lanes": lanes,
                "count": _count(phrase),
            }
        )
    return items or [{"type": raw_value.strip() or None, "generation": None, "lanes": None, "count": 1}]


# --------------------------------------------------------------------------- #
# M.2
# --------------------------------------------------------------------------- #
_M2_MENTION_RE = re.compile(r"m\.?2|m_2", re.IGNORECASE)
_M2_FORM_FACTOR_RE = re.compile(r"\b(\d{4})\b")
_M2_NVME_RE = re.compile(r"nvme", re.IGNORECASE)
_M2_SATA_RE = re.compile(r"\bsata\b", re.IGNORECASE)
_M2_PCIE_RE = re.compile(r"pcie|pci[\s-]*express", re.IGNORECASE)


def normalize_m2_slots(raw_value: str) -> list[dict]:
    items: list[dict] = []
    for phrase in _split_items(raw_value):
        if not _M2_MENTION_RE.search(phrase):
            items.append({"interface": phrase.strip() or None, "generation": None, "lanes": None, "form_factors": []})
            continue
        if _M2_NVME_RE.search(phrase) or _M2_PCIE_RE.search(phrase):
            interface = "PCIe"
        elif _M2_SATA_RE.search(phrase):
            interface = "SATA"
        else:
            # No interface stated: do NOT invent one.
            interface = None
        generation = _generation(phrase)
        lanes = _lanes(phrase)
        form_factors = _M2_FORM_FACTOR_RE.findall(phrase)
        items.append({"interface": interface, "generation": generation, "lanes": lanes, "form_factors": form_factors})
    return items or [{"interface": raw_value.strip() or None, "generation": None, "lanes": None, "form_factors": []}]


# --------------------------------------------------------------------------- #
# USB
# --------------------------------------------------------------------------- #
def _usb_parse(phrase: str) -> tuple[str | None, str | None, str | None]:
    """Return (kind, version, connector) for a USB phrase."""
    p = nfkd(phrase)
    kind = None
    version = None
    connector = None
    if re.search(r"usb\s*4|usb4", p):
        kind, version = "USB4", "4.0"
        if "type-c" in p:
            connector = "Type-C"
    elif re.search(r"usb\s*3\.2\s*gen\s*2\s*x\s*2|gen2x2", p):
        kind, version = "USB", "3.2 Gen 2x2"
        if "type-c" in p or "typec" in p:
            connector = "Type-C"
    elif re.search(r"usb\s*3\.2\s*gen\s*2|gen\s*2\b", p):
        kind, version = "USB", "3.2 Gen 2"
        if "type-c" in p or "typec" in p:
            connector = "Type-C"
    elif re.search(r"usb\s*3\.2\s*gen\s*1|gen\s*1\b", p):
        kind, version = "USB", "3.2 Gen 1"
    elif re.search(r"usb\s*3\.0", p):
        kind, version = "USB", "3.0"
    elif re.search(r"usb\s*2\.0|usb2", p):
        kind, version = "USB", "2.0"
    elif re.search(r"usb\s*1\.1", p):
        kind, version = "USB", "1.1"
    if re.search(r"type-c|typec", p):
        connector = "Type-C"
    elif re.search(r"type-a|typea", p):
        connector = "Type-A"
    return kind, version, connector


def scan_usb_ports(raw_value: str) -> list[dict]:
    """Parse a USB-centric phrase into a list of port items (for headers/counts)."""
    items: list[dict] = []
    for phrase in _split_items(raw_value):
        kind, version, connector = _usb_parse(phrase)
        count = _count(phrase)
        if kind is None:
            items.append({"kind": phrase.strip() or None, "version": None, "connector": connector, "count": count})
            continue
        items.append({"kind": kind, "version": version, "connector": connector, "count": count})
    return items or [{"kind": raw_value.strip() or None, "version": None, "connector": None, "count": 1}]


# --------------------------------------------------------------------------- #
# Rear ports / connectors
# --------------------------------------------------------------------------- #
def normalize_rear_ports(raw_value: str) -> list[dict]:
    items: list[dict] = []
    for phrase in _split_items(raw_value):
        usb = _usb_parse(phrase)
        if usb[0] is not None:
            kind, version, connector = usb
            entry: dict = {"kind": kind, "count": _count(phrase), "version": version}
            if connector:
                entry["connector"] = connector
            items.append(entry)
            continue
        if re.search(r"hdmi", phrase):
            m = re.search(r"hdmi\s*(\d+\.\d+)", nfkd(phrase))
            items.append({"kind": "HDMI", "count": _count(phrase), "version": m.group(1) if m else None})
            continue
        if re.search(r"display\s*port|displayport|\bdp\b", nfkd(phrase)):
            m = re.search(r"(?:display\s*port|displayport|dp)\s*(\d+\.\d+)", nfkd(phrase))
            items.append({"kind": "DisplayPort", "count": _count(phrase), "version": m.group(1) if m else None})
            continue
        if re.search(r"dvi", phrase):
            items.append({"kind": "DVI", "count": _count(phrase), "version": None})
            continue
        if re.search(r"\bvga\b", nfkd(phrase)):
            items.append({"kind": "VGA", "count": _count(phrase), "version": None})
            continue
        if re.search(r"jack|audio|3\.5\s*mm|headphon", nfkd(phrase)):
            items.append({"kind": "Audio", "count": _count(phrase), "version": None})
            continue
        if re.search(r"lan|ethernet|rj\s*45|2\.5g", nfkd(phrase)):
            items.append({"kind": "LAN", "count": _count(phrase), "version": None})
            continue
        items.append({"kind": phrase.strip() or None, "count": _count(phrase), "version": None})
    return items or [{"kind": raw_value.strip() or None, "count": 1, "version": None}]


# --------------------------------------------------------------------------- #
# Power connectors
# --------------------------------------------------------------------------- #
_PIN_RE = re.compile(r"(\d+)(?:\s*\+\s*(\d+))?\s*(?:-|\s)*pin", re.IGNORECASE)


def _connector_kind(phrase: str, connector_cls: str) -> str:
    p = nfkd(phrase)
    if re.search(r"\beps\b", p):
        return "EPS"
    if re.search(r"\batx12v\b|\batx\s*12", p):
        return "ATX12V"
    if re.search(r"\bpcie\b", p):
        return "PCIe"
    if re.search(r"\bsata\b", p):
        return "SATA"
    if re.search(r"\b(atx|molex|floppy)\b", p):
        return "ATX"
    return connector_cls


def normalize_power_connectors(raw_value: str, *, connector_cls: str = "ATX") -> list[dict]:
    items: list[dict] = []
    # Split on ;, / or commas; a `+` separates poles of the SAME connector.
    for phrase in _split_items(raw_value, allow_plus=False):
        kind = _connector_kind(phrase, connector_cls)
        pins_match = _PIN_RE.search(phrase)
        pins = None
        if pins_match:
            pins = int(pins_match.group(1))
            secondary = pins_match.group(2)
            if secondary:
                pins = pins + int(secondary)
        items.append({"type": kind, "pins": pins, "count": _count(phrase, ignore_pin=True)})
    return items or [{"type": connector_cls, "pins": None, "count": 1}]


# --------------------------------------------------------------------------- #
# Video
# --------------------------------------------------------------------------- #
def normalize_video(raw_value: str, *, kind: str) -> list[dict]:
    text = nfkd(raw_value)
    version = None
    if kind == "hdmi":
        m = re.search(r"hdmi\s*(\d+\.\d+)", text)
        version = m.group(1) if m else None
    else:
        m = re.search(r"(?:display\s*port|displayport|dp)\s*(\d+\.\d+)", text)
        version = m.group(1) if m else None
    count = 1
    m_count = re.search(r"(\d+)\s*(?:x|x|×)\s*(?:hdmi|display\s*port|displayport)", text)
    if m_count:
        count = int(m_count.group(1))
    return [{"version": version, "count": count}]


# --------------------------------------------------------------------------- #
# Fan headers
# --------------------------------------------------------------------------- #
_FAN_NAME_RE = re.compile(r"\b(cpu[\s_-]*fan|cpu[\s_-]*opt|opt[\s_-]*fan|aio[\s_-]*pump|pump|w[\s_-]*pump|cha(?:ssis)?[\s_-]*fan|sys[\s_-]*fan|systemfan|h\da?mp|m\.2[\s_-]*fan|vr\s*m\s*fan|fan2?\b)\b", re.IGNORECASE)
_PIN_COUNT_NOISE_RE = re.compile(r"(?:\b\d+\s*x\b|\b\d+\s*-?\s*pin\b|\b\d+\b)\s*", re.IGNORECASE)


def normalize_fan_headers(raw_value: str) -> list[dict]:
    items: list[dict] = []
    for phrase in _split_items(raw_value):
        name_match = _FAN_NAME_RE.search(phrase)
        name = None
        if name_match:
            raw_name = name_match.group(1).lower().replace("_", "-")
            if "cpu" in raw_name and "opt" in raw_name:
                name = "CPU_OPT"
            elif "cpu" in raw_name:
                name = "CPU_FAN"
            elif "opt" in raw_name:
                name = "CPU_OPT"
            elif "pump" in raw_name:
                name = "AIO_PUMP"
            elif "cha" in raw_name:
                name = "CHA_FAN"
            elif "sys" in raw_name:
                name = "SYS_FAN"
        count = _count(phrase)
        if name is None:
            cleaned = _PIN_COUNT_NOISE_RE.sub("", phrase).strip(" ")
            if cleaned:
                name = cleaned
        items.append({"name": name or (phrase.strip() or None), "count": count})
    return items or [{"name": raw_value.strip() or None, "count": 1}]


# --------------------------------------------------------------------------- #
# SATA speed canonicalization
# --------------------------------------------------------------------------- #
def normalize_sata_speed(raw_value: str) -> str | None:
    text = nfkd(raw_value)
    gbps = re.search(r"6\s*(?:gbit|gbps|gb/s|gbps)", text)
    if gbps:
        return "SATA 3.0 6 Gb/s"
    if re.search(r"sata\s*iii|sata\s*3\b|sata3|6\s*g", text):
        return "SATA 3.0 6 Gb/s"
    if re.search(r"3\s*(?:gbit|gbps|gb/s)", text) or re.search(r"sata\s*ii|sata\s*2\b|sata2|3\s*g", text):
        return "SATA 2.0 3 Gb/s"
    return None


# --------------------------------------------------------------------------- #
# Generic list of free-form features
# --------------------------------------------------------------------------- #
def normalize_string_list(raw_value: str, *, schema_key: str = "feat") -> list[dict]:
    return [{schema_key: phrase.strip().strip(".") or None} for phrase in _split_items(raw_value) if phrase.strip()]


def normalize_connector_headers(raw_value: str, *, extra: tuple[str, ...] = ()) -> list[dict]:
    items: list[dict] = []
    for phrase in _split_items(raw_value):
        pins_match = _PIN_RE.search(phrase)
        items.append(
            {
                "type": phrase.strip(" .") or None,
                "count": _count(phrase),
                **({"pins": int(pins_match.group(1))} if pins_match else {}),
            }
        )
    items = items or [{"type": raw_value.strip() or None, "count": 1}]
    # deduplicate by type preserving first-seen order
    seen: set[str] = set()
    deduped: list[dict] = []
    for it in items:
        marker = str(it.get("type"))
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(it)
    return deduped


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
_FEATURE_KEYS = {"audio_features", "rgb_features", "onboard_buttons", "front_panel_headers"}


def _parse_structured(value: str) -> list[Any] | None:
    """Return the items of a raw value that is already structured data.

    The LLM (or a data-rich source page) sometimes returns the value for a
    ``json`` definition already serialized as a JSON array/object (either
    double-quoted JSON or a single-quoted Python literal).  Trying to split that
    text with the human-phrase parser mangles it.  When detected, we normalize
    each element independently so nothing is corrupted.
    """
    text = value.strip()
    if not text.startswith(("[", "{")):
        return None
    parsed = None
    try:
        parsed = json.loads(text)
    except Exception:
        try:
            parsed = ast.literal_eval(text)
        except Exception:
            return None
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return None
    items: list[Any] = []
    for item in parsed:
        if isinstance(item, (dict, list)):
            items.append(item)
        elif isinstance(item, str):
            items.append(item)
    return items


def _structured_to_phrase(item: dict) -> str:
    """Flatten one structured object into a single human-readable phrase."""
    parts: list[str] = []
    for value in item.values():
        if isinstance(value, (list, tuple)):
            parts.extend(str(v) for v in value if v is not None)
        elif isinstance(value, dict):
            parts.append(_structured_to_phrase(value))
        elif value is not None:
            parts.append(str(value))
    return " ".join(part for part in parts if part.strip())


def _apply_handler_per_item(handler, structured_items: list[Any], definition_key: str | None = None) -> list[dict]:
    """Run a per-item normalizer for each structured element and merge results.

    Normalizing each element independently avoids the comma-splitting that
    corrupts a serialized list of objects, and de-duplicates identical items.
    """
    out: list[dict] = []
    for item in structured_items:
        if isinstance(item, dict) and definition_key == "fan_header_list":
            name = item.get("name") or item.get("type")
            count = item.get("count")
            if name:
                out.extend(normalize_fan_headers(str(name)))
                if isinstance(count, int) and out:
                    out[-1]["count"] = count
                continue
        phrase = _structured_to_phrase(item) if isinstance(item, dict) else str(item).strip()
        if not phrase:
            continue
        out.extend(handler(phrase))
    seen: set[str] = set()
    deduped: list[dict] = []
    for entry in out:
        marker = json.dumps(entry, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(entry)
    return deduped


def normalize_to_json(definition_key: str, raw_value: str, item_schema: dict | None = None) -> list[dict]:
    """Dispatch a raw string to the structured form for the given definition key.

    Returns a list of dicts.  Unknown keys degrade to a single item with the raw
    string so the evidence is never lost and nothing is invented.
    """
    value = (raw_value or "").strip()
    if not value:
        return []
    by_key = {
        "pcie_slot_list": lambda v=value: normalize_pcie_slots(v),
        "m2_slot_list": lambda v=value: normalize_m2_slots(v),
        "rear_ports": lambda v=value: normalize_rear_ports(v),
        "motherboard_power_connector": lambda v=value: normalize_power_connectors(v, connector_cls="ATX"),
        "cpu_power_connector_types": lambda v=value: normalize_power_connectors(v, connector_cls="ATX12V"),
        "auxiliary_power_connectors": lambda v=value: normalize_power_connectors(v, connector_cls="ATX12V"),
        "pcie_power_connectors": lambda v=value: normalize_power_connectors(v, connector_cls="PCIe"),
        "footer_headers": lambda v=value: normalize_connector_headers(v),
        "fan_header_list": lambda v=value: normalize_fan_headers(v),
        "sata_headers": lambda v=value: normalize_connector_headers(v),
        "usb_headers": lambda v=value: scan_usb_ports(v),
        "audio_headers": lambda v=value: normalize_connector_headers(v),
    }
    handler = by_key.get(definition_key)
    structured_items = _parse_structured(value)
    if handler and structured_items is not None:
        return _apply_handler_per_item(handler, structured_items, definition_key)
    if definition_key in {"hdmi", "displayport"}:
        return normalize_video(value, kind=definition_key)
    if handler:
        return handler()
    if structured_items is not None:
        return structured_items
    if "feat" in (item_schema or {}):
        schema_key = next(iter(item_schema.keys()))
        return normalize_string_list(value, schema_key=schema_key)
    if definition_key in _FEATURE_KEYS:
        return normalize_string_list(value)
    return [{"value": value}]
