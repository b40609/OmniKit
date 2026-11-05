"""評估漏斗共用的 GitHub 查詢。

優先用已登入的 gh，其次 GITHUB_TOKEN 環境變數；都沒有才用未登入（每小時 60 次，而且沒有 GraphQL）。
金鑰只從 gh 或環境變數取用，不印出、不寫檔。查不到（404）回 None，額度用完或其他錯誤丟 GitHubError，
呼叫端把它記成「未知」，不當作通過。
"""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


class GitHubError(Exception):
    pass


def detect():
    gh = shutil.which("gh")
    if gh and subprocess.run([gh, "auth", "status"], capture_output=True).returncode == 0:
        return "gh"
    if os.environ.get("GITHUB_TOKEN"):
        return "token"
    return "anonymous"


class Client:
    """mode：gh、token 或 anonymous。search_pause 是兩次搜尋之間的秒數（搜尋每分鐘只能 30 次）。"""

    def __init__(self, mode=None, search_pause=2.1):
        self.mode = mode or detect()
        self.search_pause = search_pause
        self._last_search = 0.0

    @property
    def has_graphql(self):
        return self.mode != "anonymous"

    def rest(self, path, raw=False):
        accept = "application/vnd.github.raw" if raw else "application/vnd.github+json"
        if self.mode == "gh":
            result = subprocess.run(
                ["gh", "api", "-H", f"Accept: {accept}", path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0:
                if "HTTP 404" in result.stderr:
                    return None
                raise GitHubError(result.stderr.strip()[-300:] or f"gh api {path} 失敗")
            return result.stdout if raw else (json.loads(result.stdout) if result.stdout.strip() else None)
        return self._http("GET", path, accept=accept, raw=raw)

    def graphql(self, query, variables=None):
        """回傳 data；個別 alias 查不到時 data 裡是 null（GraphQL 的部分錯誤不丟例外）。"""
        if not self.has_graphql:
            raise GitHubError("未登入不能用 GraphQL：請先 gh auth login，或設定 GITHUB_TOKEN")
        body = json.dumps({"query": query, "variables": variables or {}})
        if self.mode == "gh":
            result = subprocess.run(
                ["gh", "api", "graphql", "--input", "-"], input=body,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            try:
                doc = json.loads(result.stdout)
            except json.JSONDecodeError:
                raise GitHubError(result.stderr.strip()[-300:] or "GraphQL 沒有回應") from None
        else:
            doc = self._http("POST", "graphql", body=body.encode())
        if doc.get("data") is None:
            raise GitHubError(json.dumps(doc.get("errors"), ensure_ascii=False)[:300])
        return doc["data"]

    def _pace(self):
        wait = self.search_pause - (time.monotonic() - self._last_search)
        if wait > 0:
            time.sleep(wait)
        self._last_search = time.monotonic()

    def search_issues(self, query, limit=8):
        """依留言數排序；回傳精簡過的 issue（內文只留前 500 字）。"""
        self._pace()
        doc = self.rest(f"search/issues?q={urllib.parse.quote(query)}&sort=comments&order=desc&per_page={limit}")
        return [
            {"title": i["title"], "url": i["html_url"], "author": (i.get("user") or {}).get("login", ""),
             "association": i.get("author_association", ""), "published": (i.get("created_at") or "")[:10],
             "state": i.get("state", ""), "comments": i.get("comments", 0), "excerpt": (i.get("body") or "")[:500]}
            for i in (doc or {}).get("items", [])
        ]

    def search_repos(self, query, limit=5):
        self._pace()
        doc = self.rest(f"search/repositories?q={urllib.parse.quote(query)}&per_page={limit}")
        return [
            {"repo": r["full_name"], "description": (r.get("description") or "")[:200],
             "stars": r["stargazers_count"], "pushed": (r.get("pushed_at") or "")[:10], "archived": r["archived"]}
            for r in (doc or {}).get("items", [])
        ]

    def _http(self, method, path, accept="application/vnd.github+json", raw=False, body=None):
        headers = {"Accept": accept, "User-Agent": "omnikit-eval"}
        token = os.environ.get("GITHUB_TOKEN") if self.mode == "token" else None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(f"{API}/{path}", data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (403, 429):
                raise GitHubError(f"GitHub 回 {e.code}：額度用完，或需要登入（gh auth login／GITHUB_TOKEN）") from None
            raise GitHubError(f"GitHub 回 {e.code}") from None
        except urllib.error.URLError as e:
            raise GitHubError(f"連不到 GitHub：{e.reason}") from None
        return text if raw else (json.loads(text) if text.strip() else None)


class Fake:
    """自我測試用：rest 依路徑、graphql 依呼叫函式回傳預先準備的資料，不連網。"""

    def __init__(self, rest=None, graphql=None, search=None, mode="gh", issues=None):
        self.mode, self._rest, self._graphql, self._search = mode, rest or {}, graphql, search or {}
        self._issues = issues or {}
        self.calls = []

    def search_issues(self, query, limit=8):
        self.calls.append(("issues", query))
        return self._issues.get(query.split()[0], [])[:limit]

    has_graphql = Client.has_graphql

    def rest(self, path, raw=False):
        self.calls.append(("rest", path))
        value = self._rest.get(path)
        if isinstance(value, Exception):
            raise value
        return value

    def graphql(self, query, variables=None):
        self.calls.append(("graphql", query[:40]))
        if not self.has_graphql:
            raise GitHubError("未登入不能用 GraphQL")
        return self._graphql(query, variables or {})

    def search_repos(self, query, limit=5):
        self.calls.append(("search", query))
        return self._search.get(query, [])[:limit]
