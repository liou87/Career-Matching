"""
按规则从标注的技能名派生匹配用的别名，不调模型，结果可复现。

模型写的差距和标注措辞常常不同（「Solr」对「Solr项目经验」），只用技能名本身做子串匹配，
召回率会被措辞差异压低。规则：
- 去掉「项目经验」「经验」「经历」后缀
- 按「/」「、」「或」「及」「与」拆成几项，每项单独作为别名
- 括号里外各算一个别名：「Infrastructure as Code (IaC)」→ IaC
- 补几个公认的同义写法：Go/Golang、Kubernetes/K8s

运行（在 backend 目录下）：
    python -m evals.aliases        # 给 labels.json 每条差距补上派生别名，已有别名保留
"""
import json
import re
from pathlib import Path

from evals.label_ui import DATASET_DIR, save

SUFFIXES = ("项目经验", "经验", "经历")
# 「以及」整体拆；「参与」「及时」里的字不拆
SEPARATORS = re.compile(r"以及|(?<!参)与|及(?!时)|或|[/、，,]")
SYNONYMS = {"go": ["Golang"], "golang": ["Go"], "kubernetes": ["K8s"], "k8s": ["Kubernetes"]}


def _strip_suffix(text: str) -> str:
    for suffix in SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)].strip()
    return text


def derive_aliases(skill: str) -> list[str]:
    """技能名本身在第一位，后面是派生出的别名，去重，丢掉不到 2 个字符的片段。"""
    skill = skill.strip()
    base = _strip_suffix(skill)
    candidates = [skill, base]
    paren = re.search(r"[(（]([^)）]+)[)）]", base)
    if paren:
        candidates += [paren.group(1), base[: paren.start()] + base[paren.end():]]
    candidates += [_strip_suffix(part.strip()) for part in SEPARATORS.split(base)]
    candidates += [s for c in candidates for s in SYNONYMS.get(c.strip().lower(), [])]

    out: list[str] = []
    for c in candidates:
        c = c.strip()
        if len(c) >= 2 and c.lower() not in {x.lower() for x in out}:
            out.append(c)
    return out


def expand(labels: list[dict]) -> int:
    """原地给每条差距补派生别名，返回新增的别名数。"""
    added = 0
    for entry in labels:
        for m in entry["missing"]:
            existing = {a.lower() for a in m["aliases"]}
            new = [a for a in derive_aliases(m["skill"]) if a.lower() not in existing]
            m["aliases"] += new
            added += len(new)
    return added


def main():
    path = DATASET_DIR / "labels.json"
    labels = json.loads(Path(path).read_text(encoding="utf-8"))
    added = expand(labels)
    save(path, labels)
    print(f"新增 {added} 个别名，已写回 {path}")


if __name__ == "__main__":
    main()
