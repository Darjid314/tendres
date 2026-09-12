import importlib.util
from pathlib import Path


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, Path(relative_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


squ = load_module("scrape_squ_tenders", "scripts/scrape_squ_tenders.py")
exporter = load_module("export_dashboard_data", "scripts/export_dashboard_data.py")


def test_squ_table_parser_preserves_notice_url_and_source():
    html = '''<table><tr><th>Tender No</th><th>Tender Title</th><th>Closing Date</th></tr>
    <tr><td>42/2026</td><td><a href="/tenders/42">Network refresh tender</a></td><td>30-09-2026</td></tr></table>'''
    tenders = squ.parse_tenders(html, "https://www.squ.edu.om/tenders")
    assert len(tenders) == 1
    assert tenders[0]["tender_no"] == "42/2026"
    assert tenders[0]["tender_url"] == "https://www.squ.edu.om/tenders/42"
    assert tenders[0]["source"] == "Sultan Qaboos University"


def test_tender_identity_includes_source():
    assert exporter.tender_key("123", "Oman Tender Board") != exporter.tender_key("123", "Sultan Qaboos University")
    assert exporter.tender_key("123", "") == "Oman Tender Board:123"
