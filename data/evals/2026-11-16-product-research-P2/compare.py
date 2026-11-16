"""三邊（免費管道、WebSearch、Exa）相關工具名的比對；名字用 sweep.py 的 key_of／seen_before 比（短名對得上就算同一個）。

用法：python -I compare.py <帳本.json>    印比對結果（compare.json 就是這個輸出），名字順便記進帳本
名單是人工從 out/ 的原始結果與 sweep.py channels 的輸出挑的，標準見評估紀錄。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "engine" / "skills" / "omnikit-research" / "scripts"))
import sweep  # noqa: E402

G = ["repo visualization tool", "codebase diagram generator", "agent skill architecture diagram from codebase"]
FREE = {  # 管道: 名字（每組）
    G[0]: {"skills-sh": ["fadhlirahim/codebase-map"], "github-topic": ["mohamedsci/project-structure-tree-generator"],
           "hn": ["Paradigm"]},
    G[1]: {"github-topic": ["ahmedkhaleel2004/gitdiagram", "jfeliu007/goplantuml"],
           "github-keyword": ["arrufat/meduza", "bb-boy680/open-zread", "amz34/archmap", "helloiamlee/repomap",
                              "arthurmgraf/claude-diagram-generator", "techdeveloper-org/mcp-uml-diagram",
                              "yusufguzeldere/codebase-architect-agent"],
           "hn": ["bkryza/clang-uml", "tensorush/meduza", "Eraser", "CodeViz", "Composer", "codeboarding/codeboarding",
                  "smeghead/php-class-diagram", "Auto Wiki", "JigsawML"]},
    G[2]: {"github-topic": ["tt-a1i/archify", "ahmedkhaleel2004/gitdiagram", "agents365-ai/drawio-skill",
                            "sverweij/dependency-cruiser", "haydenschmitty/floorplan", "patrickchugh/terravision",
                            "aryanutkarsh/seecode", "lazypay/archscribe"],
           "skills-sh": ["inkboard/system-atlas", "shibainu0817/draw-c4-skill", "dp-archive/archive",
                         "zebbern/claude-code-guide"],
           "npm": ["@archme/cli"]},
}
WEB = {
    G[0]: ["coder-ralph/repotree", "madhurjindal/github-repo-visualizer", "MapMyRepo", "githubocto/repo-visualizer",
           "visualize-repo", "StructViz", "GitProbe", "Graphify"],
    G[1]: ["vedantparmar12/document-automation", "Eraser", "tensorush/meduza", "codetwin", "repoarch",
           "pjaerr/code-flow-extension", "diagram-gen", "diagramgen", "zebbern/claude-code-guide",
           "codeboarding/codeboarding", "arkit", "swark-io/swark", "Architecture Diagram Generator (mcpmarket)",
           "Software Ideas Modeler", "seandearnaley/code-diagram-generator", "excalidraw-diagram-generator",
           "sopaco/smart-docs", "mikegazzaruso/codemap", "Vxplain"],
    G[2]: ["thomasgauvin/codebase-architecture-analysis", "agentera/agently", "athola/claude-night-market",
           "tt-a1i/archify", "donbr/skills", "oimiragieo/agent-studio", "mgiovani/cc-arsenal",
           "imperialautomation/claude-code-toolkit", "dp-archive/archive"],
}
EXA = {
    G[0]: ["Gitvize", "Visual Anything", "ahmedkhaleel2004/gitdiagram", "Grappl", "corvidlabs/fledge-plugin-atlas",
           "RepoGraph", "gitcgr", "RepoSense", "GitScope"],
    G[1]: ["DataDef", "ArchToCode", "Codesplain", "Codebase Mermaid Generator", "ahmedkhaleel2004/gitdiagram",
           "Atomic Viz", "CodeArchy", "sudokatie/cartographer", "Code2Graph", "Taskade code to architecture diagram"],
    G[2]: ["lewes2/archpresent", "nedeadinside/likec4-skill", "jatinbhargava/repo-architecture-skill",
           "shibainu0817/draw-c4-skill", "ccalita/graphviz-dive", "yaambe/synopsis",
           "konraddzbik/architecture-diagram-skill", "beadnall/codemap", "wyxnick/agent-mermaid-skill",
           "laneparton/document-flows", "agents365-ai/drawio-skill"],
}


def keys(names):
    out = []
    for n in names:
        k = sweep.key_of(n)
        ks, ss = set(out), {sweep.short(x) for x in out}
        if not sweep.seen_before(k, ks, ss):
            out.append(k)
    return out


def minus(a, b):
    ks, ss = set(b), {sweep.short(x) for x in b}
    return [x for x in a if not sweep.seen_before(x, ks, ss)]


free_all = keys([n for g in G for ns in FREE[g].values() for n in ns])
web_all = keys([n for g in G for n in WEB[g]])
exa_all = keys([n for g in G for n in EXA[g]])
res = {
    "per_group": {g: {"free": len(keys([n for ns in FREE[g].values() for n in ns])), "web": len(keys(WEB[g])),
                      "exa": len(keys(EXA[g])),
                      "exa_new": minus(keys(EXA[g]), free_all + web_all),
                      "web_new": minus(keys(WEB[g]), free_all + exa_all)} for g in G},
    "totals": {"free": len(free_all), "web": len(web_all), "exa": len(exa_all),
               "union": len(keys(free_all + web_all + exa_all))},
    "exa_new": minus(exa_all, free_all + web_all),
    "web_new": minus(web_all, free_all + exa_all),
    "free_new": minus(free_all, web_all + exa_all),
    "overlap_exa_web": [x for x in exa_all if x not in minus(exa_all, web_all)],
    "overlap_exa_free": [x for x in exa_all if x not in minus(exa_all, free_all)],
    "overlap_web_free": [x for x in web_all if x not in minus(web_all, free_all)],
}
for k in ("exa_new", "web_new", "free_new"):
    res[k + "_n"] = len(res[k])
print(json.dumps(res, ensure_ascii=False, indent=1))

# 記進帳本（免費管道 + WebSearch；Exa 另記成 exa 管道，給 status 看三邊合起來的新名字）
ledger_path = Path(sys.argv[1])
ledger = sweep.load(ledger_path)
for g in G:
    for ch, ns in FREE[g].items():
        sweep.record(ledger, g, ch, ns)
    sweep.record(ledger, g, "web-en", WEB[g])
    sweep.record(ledger, g, "exa", EXA[g])
sweep.save(ledger_path, ledger)
