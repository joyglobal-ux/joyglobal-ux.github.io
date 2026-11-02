"""Polaris PWA 스니펫(_pwa/snippet.html)을 페이지 <head>에 넣거나 갱신한다.

사용: python3 _pwa/inject.py <html 또는 .py 템플릿 경로>...
- 이미 <!-- polaris-app:start --> ~ <!-- polaris-app:end --> 블록이 있으면 통째로 교체, 없으면 </head> 바로 앞에 삽입.
- viewport 메타에 viewport-fit=cover를 붙인다.
- .py(f-string HTML 템플릿, 예: etf-tracker/kosdaq_etf_tracker.py)는 중괄호를 {{ }}로 이스케이프해서 넣는다.
"""
import re, sys, pathlib

SNIP = (pathlib.Path(__file__).parent / "snippet.html").read_text(encoding="utf-8").strip()
BLOCK = re.compile(r"<!-- polaris-app:start.*?<!-- polaris-app:end -->", re.S)
VIEW = re.compile(r'(<meta name="viewport" content="width=device-width,\s*initial-scale=1(?:\.0)?)(")')

for arg in sys.argv[1:]:
    p = pathlib.Path(arg)
    src = p.read_text(encoding="utf-8")
    snip = SNIP.replace("{", "{{").replace("}", "}}") if p.suffix == ".py" else SNIP
    if BLOCK.search(src):
        out = BLOCK.sub(lambda m: snip, src, count=1)
    else:
        assert src.count("</head>") == 1, f"{p}: </head> 가 정확히 1개가 아님"
        out = src.replace("</head>", snip + "\n</head>", 1)
    if "viewport-fit=cover" not in out:
        out, n = VIEW.subn(r"\1, viewport-fit=cover\2", out, count=1)
        assert n == 1, f"{p}: viewport 메타를 못 찾음"
    if out != src:
        p.write_text(out, encoding="utf-8")
        print("updated", p)
    else:
        print("same   ", p)
