#!/usr/bin/env python3
"""check_links.py — 链接核验：状态码、重定向链、区分真失效与反爬拦截

用法:
  check_links.py URL [URL...]
  check_links.py --from-file FILE   （每行一个 URL；也支持从整段文本自动提取）

输出（stdout，TSV）:
  url | final_url | status | redirects | verdict
  verdict: OK / DEAD(404) / BOT_SUSPECT(需浏览器人工复核) / ERROR

设计要点：403/406/429 多数是反爬拦截而非失效（如 cisecurity.org 对 curl 返回 403），
先用普通 UA 请求，被拦后换浏览器 UA 重试一次，仍被拦则标 BOT_SUSPECT——这与
"确认失效"的处置完全不同。
"""

import sys, re, ssl, urllib.request, urllib.error
from urllib.parse import urljoin

UA_PLAIN = "python-urllib/doc-review"
UA_BROWSER = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
REDIR = {301, 302, 303, 307, 308}


class NoAutoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, ua):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    opener = urllib.request.build_opener(
        NoAutoRedirect, urllib.request.HTTPSHandler(context=ctx)
    )
    try:
        resp = opener.open(req, timeout=25)
        return resp.status, resp.geturl(), resp.headers.get("Location")
    except urllib.error.HTTPError as e:
        return e.code, url, e.headers.get("Location") if e.headers else None
    except Exception as e:
        return None, url, f"{type(e).__name__}: {e}"


def check(url):
    chain, current, ua = [], url, UA_PLAIN
    for _ in range(10):
        status, final, loc = fetch(current, ua)
        if status is None:
            return url, current, "-", " → ".join(chain) or "-", f"ERROR({final})"
        if status in REDIR and loc:
            chain.append(f"{status}→{loc}")
            current = urljoin(
                current, loc
            )  # Location 可能是相对路径，必须按当前 URL 解析
            continue
        if status in (403, 406, 429) and ua == UA_PLAIN:
            ua = UA_BROWSER  # 换浏览器 UA 重试一次
            chain.append(f"{status}(retry with browser UA)")
            continue
        break
    if 200 <= status < 300:
        verdict = "OK"
    elif status == 404:
        verdict = "DEAD(404)"
    elif status in (403, 406, 429):
        verdict = "BOT_SUSPECT(需浏览器人工复核)"
    else:
        verdict = f"HTTP({status})"
    return url, current, str(status), " → ".join(chain), verdict


def extract_urls(text):
    return re.findall(r"https?://[^\s)\]、,，。；;）」\']+", text)


def main():
    urls = []
    if sys.argv[1] == "--from-file":
        text = open(sys.argv[2], encoding="utf-8", errors="ignore").read()
        urls = extract_urls(text)
    else:
        urls = sys.argv[1:]
    if not urls:
        print(__doc__)
        sys.exit(1)
    print("url\tfinal_url\tstatus\tredirects\tverdict")
    counts = {}
    for u in urls:
        u = u.rstrip(".,;")
        try:
            r = check(u)
        except Exception as e:
            r = (u, u, "-", "-", f"ERROR({type(e).__name__}: {e})")
        print("\t".join(r))
        v = r[4].split("(")[0]
        counts[v] = counts.get(v, 0) + 1
    print(f"# summary: {dict(counts)} of {len(urls)}")


if __name__ == "__main__":
    main()
