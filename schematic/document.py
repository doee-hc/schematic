"""Schematic document load and normalization."""

import json


def normalize_document(data):
    if not isinstance(data, dict) or not isinstance(data.get("root"), dict):
        raise ValueError("电路图 JSON 需要对象根，且包含 root")
    data.setdefault("palette", {})
    data.setdefault("swatches", [])
    return data


def load_document(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return normalize_document(data)
