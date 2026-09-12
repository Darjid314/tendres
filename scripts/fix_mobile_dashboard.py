from pathlib import Path

MARKER = "<!-- MOBILE_LAYOUT_FIX_V1 -->"
CSS = f'''\n<style id="mobile-layout-fix">\n{MARKER}\nhtml,body{{width:100%;max-width:100%;overflow-x:hidden}}\n.app{{width:100%;min-width:0}}\n.sources,.kpis,.analytics,.toolbar,.list{{min-width:0;max-width:100%}}\n.source,.kpi,.panel,.tender{{min-width:0;max-width:100%}}\n.source-head,.tender-top{{min-width:0}}\n.source-name,.source-msg,.source-time,.title,.no,.deadline{{overflow-wrap:anywhere;word-break:break-word}}\n@media(max-width:900px){{\n  .sources{{grid-template-columns:1fr!important}}\n}}\n@media(max-width:700px){{\n  .section-title{{align-items:flex-start;gap:10px;flex-wrap:wrap}}\n  .section-title span{{flex:1 1 100%}}\n  .analytics{{grid-template-columns:1fr}}\n  .toolbar{{grid-template-columns:1fr}}\n}}\n@media(max-width:460px){{\n  .kpis{{grid-template-columns:1fr}}\n}}\n</style>\n'''


def patch(path: str) -> bool:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    marker = "</style>"
    if marker not in text:
        raise RuntimeError(f"No </style> marker found in {path}")
    text = text.replace(marker, marker + CSS, 1)
    p.write_text(text, encoding="utf-8")
    return True


changed = []
for target in ("docs/dashboard_multi_source.html",):
    if patch(target):
        changed.append(target)

print("Mobile dashboard layout patch applied." if changed else "Mobile dashboard layout patch already present.")
