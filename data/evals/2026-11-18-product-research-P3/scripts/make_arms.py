"""P3 各組名單（主控整理）。B、C 的名字照報告裡推薦的工具逐一收，同一個工具只收一次。

規則：
- 連結不存在、工具也查不到的（gh api 404、擴充 ID 不存在、網域連不上、佔位字串 yourusername、example.com）
  名字後面加「（編造）」，免得靠名字碰巧對上 A 的真工具。核對紀錄在 data/linkcheck*.json、linkcheck-B2.txt。
- 工具是真的、只是連結錯的（Code2Flow、Madge、C1 的 Archify、pipdeptree、KubeDiagrams、Cloudiscovery），照名字收。
- 同一家的產品（Eraser AI 對 A 的 eraser-git-diagrammer、NanoAPI Cloud 對 A 的 nanoapi-io/napi）用 A 的名字，
  不重複計算。

用法：python -I -X utf8 make_arms.py <A-names.tsv> <輸出 arms.json>
"""
import json
import sys

B1 = ["GitHub Copilot", "Code Outline", "CodeScene", "Sourcegraph", "Dependency Cruiser", "Graphviz"]
B2 = ["Code2Flow", "CodeMap (Microsoft)", "CodeGraph (GitHub)（編造）", "Dependency-Tree", "SonarQube", "CodeScene",
      "CodeDepend（編造）", "CodeMap.io（編造）", "PlantUML"]
C1 = ["GitDiagram", "Dependency Cruiser", "Madge", "pipdeptree", "ReShaper（編造）", "Structurizr", "C4Modeler（編造）",
      "Code2Diagram（編造）", "Archi", "tanchaowen84/flowchartai", "eraser-git-diagrammer", "Code2Flow", "Mermaid Chart",
      "codetoflow.com", "Mermaid CLI", "VS Code Mermaid Extension（編造）", "readme-md-diagram（編造）",
      "GitHub Actions + Mermaid", "diagram-creator（編造）", "Graphviz", "Mermaid", "D2", "Architecture Review Agent",
      "Archify", "CodeScene", "Codemaps（編造）", "Apex Code Diagrammer", "Azure Application Insights", "New Relic",
      "nanoapi-io/napi", "amitfounderspace/CodeXray", "likec4", "Datadog", "Dynatrace", "Splunk Observability Cloud",
      "Comet", "IBM Cloud Pak for Applications", "ShiftLeft", "Snyk", "Black Duck", "Mermaid Live Preview（編造）",
      "PlantUML", "Architecture Diagrams VS Code 擴充（編造）", "Mermaid Markdown", "GitHub Action for Mermaid",
      "kajitiluna/erd-designer", "BOCOVO/db-schema-visualizer", "ModelMapper", "dineug/erd-editor",
      "dbdiagram VS Code（編造）", "draw.io", "C4 Model Tools", "GitHub Actions + Diagram Generators",
      "mingrammer/diagrams", "KubeDiagrams", "HariSekhon/Diagrams-as-Code", "AI Diagram Maker", "Cloudiscovery",
      "BrainTool", "E-R Generator", "VPasCode（編造）", "Query-Driven UML Generator", "EulerViz（編造）",
      "CodeVenn（編造）", "Graphviz with Euler Plugins", "MCP Euler Generator（編造）", "VS Code Euler Extension（編造）",
      "DiagramGen（編造）", "CodeGraph VS Code 擴充（編造）", "AI Architect（編造）", "ModelCraft", "Structure101",
      "CAST APM", "CodeQL", "GitHub Dependency Graph"]
C2 = ["GitDiagram", "repowise-dev/repowise", "eraser-git-diagrammer", "archtocode", "tt-a1i/archify",
      "sparklabx/drawio-ai-kit", "sverweij/dependency-cruiser", "Auryngji/DepViz-Dependency-Visualizer", "Mertcikla/tld",
      "swark-io/swark", "c4hero/c4hero", "diagrams-as-code (Community Tools)", "Mermaid", "PlantUML",
      "mingrammer/diagrams", "Mermaid Live", "RepoGraph（編造）", "Mermaid-Repo-Parser（編造）", "CodeDiagram（編造）",
      "RepoMind（編造）", "CodeGraph（編造）", "Architector（編造）", "GitStruct（編造）", "RepoVisualizer（編造）",
      "CodeNarrator（編造）", "MCP-ArchGen（編造）", "RepoSynth（編造）", "DocStruct（編造）", "ArchiLang（編造）",
      "CodeGraphAI（編造）", "Mermaid-AI（編造）", "MCP-Draw（編造）", "PlantUML GitHub Action（編造）",
      "PlantUML for VS Code（編造）", "UMLet", "draw.io", "GitHub Codespaces with PlantUML CLI", "Code2Diagram（編造）",
      "ArchUnit", "Mermaid CLI", "Code2Flow", "Cocoon-AI/architecture-diagram-generator"]

rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1], encoding="utf-8")][1:]
arms = {"A": [r[0] for r in rows], "B1": B1, "B2": B2, "C1": C1, "C2": C2}
for k, v in arms.items():
    assert len(v) == len(set(v)), (k, [x for x in v if v.count(x) > 1])
json.dump(arms, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print({k: len(v) for k, v in arms.items()}, "編造：", {k: sum(1 for x in v if "編造" in x) for k, v in arms.items()})
