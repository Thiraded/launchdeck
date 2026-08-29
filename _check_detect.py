import wc_core as core
m = core.load_manifest()
print("=== live detection check (read-only, no windows opened) ===")
for w in m["works"]:
    if w.get("detect") is False:
        continue
    toks = core.titles_for(w)
    print(f"  {w['id']:16s} match={toks}  running={core.is_running(w)}")
print("\nDONE (read-only)")
