from pathlib import Path

MARKER = "<!-- MOBILE_LAYOUT_FIX_V2 -->"
CSS = f'''\n<style id="mobile-layout-fix">\n{MARKER}\nhtml,body{{width:100%;max-width:100%;overflow-x:hidden}}\n*,*::before,*::after{{box-sizing:border-box}}\n.app{{width:100%;min-width:0;max-width:1440px;overflow-x:hidden}}\n.sources,.kpis,.analytics,.toolbar,.list{{width:100%;min-width:0;max-width:100%}}\n.source,.kpi,.panel,.tender{{min-width:0;max-width:100%;overflow:hidden}}\n.source-head,.tender-top{{min-width:0;max-width:100%}}\n.source-name,.source-msg,.source-time,.title,.no,.deadline{{min-width:0;overflow-wrap:anywhere;word-break:break-word}}\n@media(max-width:1200px){{\n  .sources{{grid-template-columns:1fr!important}}\n}}\n@media(max-width:700px){{\n  .app{{padding:13px}}\n  .section-title{{align-items:flex-start;gap:10px;flex-wrap:wrap}}\n  .section-title span{{flex:1 1 100%;min-width:0}}\n  .analytics{{grid-template-columns:1fr}}\n  .toolbar{{grid-template-columns:1fr}}\n  .tender-top{{flex-direction:column}}\n}}\n@media(max-width:460px){{\n  .kpis{{grid-template-columns:1fr}}\n}}\n</style>\n'''


def patch(path: str) -> bool:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    # Remove any previous versions of this runtime patch so repeated workflow runs
    # never accumulate conflicting CSS blocks.
    start = text.find('<style id="mobile-layout-fix">')
    if start != -1:
        end = text.find('</style>', start)
        if end != -1:
            end += len('</style>')
            text = text[:start] + text[end:]
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

print("Mobile dashboard layout patch V2 applied." if changed else "Mobile dashboard layout patch already present.")
