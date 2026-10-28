#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
from pathlib import Path


class DataUtils:
    @staticmethod
    def save_json(path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def load_json(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    @staticmethod
    def get_cache(path):
        # Same read-if-present behavior as recovered cache_dataflow_function.py.
        return DataUtils.load_json(path) if Path(path).is_file() else {}
