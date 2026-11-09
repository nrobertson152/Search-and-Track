#!/usr/bin/env python3
"""Insert name_ru = "..." after matching name = "..." lines of a theater file.

Usage: python tools/add_name_ru.py data/theaters/<id>/theater.toml MAPPING.json
The mapping is English name -> Russian name. Existing name_ru lines are replaced."""
import json
import re
import sys

path, mp = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))
out = []
for ln in open(path, encoding="utf-8").read().split("\n"):
    if ln.startswith("name_ru = "):
        continue
    out.append(ln)
    m = re.match(r'^name = "(.*)"$', ln)
    if m and m.group(1) in mp:
        out.append(f'name_ru = "{mp[m.group(1)]}"')
open(path, "w", encoding="utf-8").write("\n".join(out))
