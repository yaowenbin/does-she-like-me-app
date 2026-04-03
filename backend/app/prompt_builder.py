from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from .skills_bundle import resolve_skill_root


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


_PROMPT_FILES: tuple[str, ...] = (
    "prompts/safety_refusal.md",
    "prompts/analyze_segments.md",
    "prompts/score_rubric.md",
    "prompts/lens_evolution.md",
    "prompts/lens_gene_rhetoric.md",
    "prompts/lens_psychology.md",
    "prompts/lens_literature.md",
    "prompts/lens_astrology.md",
    "prompts/lens_attainability.md",
    "prompts/synthesis.md",
    "reference.md",
)

_PROMPT_CACHE: dict[str, tuple[Tuple[int, ...], Dict[str, str]]] = {}


def _prompt_fingerprint(skill_root: Path) -> Tuple[int, ...]:
    out: list[int] = []
    for rel in _PROMPT_FILES:
        p = skill_root / rel
        st = p.stat()
        out.append(st.st_mtime_ns)
        out.append(st.st_size)
    return tuple(out)


def _load_prompt_bundle(skill_root: Path) -> Dict[str, str]:
    key = str(skill_root.resolve())
    fp = _prompt_fingerprint(skill_root)
    cached = _PROMPT_CACHE.get(key)
    if cached and cached[0] == fp:
        return cached[1]
    bundle = {
        "safety": _read_text(skill_root / "prompts" / "safety_refusal.md"),
        "evidence": _read_text(skill_root / "prompts" / "analyze_segments.md"),
        "rubric": _read_text(skill_root / "prompts" / "score_rubric.md"),
        "lens_evo": _read_text(skill_root / "prompts" / "lens_evolution.md"),
        "lens_gene": _read_text(skill_root / "prompts" / "lens_gene_rhetoric.md"),
        "lens_psy": _read_text(skill_root / "prompts" / "lens_psychology.md"),
        "lens_lit": _read_text(skill_root / "prompts" / "lens_literature.md"),
        "lens_ast": _read_text(skill_root / "prompts" / "lens_astrology.md"),
        "lens_att": _read_text(skill_root / "prompts" / "lens_attainability.md"),
        "synthesis": _read_text(skill_root / "prompts" / "synthesis.md"),
        "reference": _read_text(skill_root / "reference.md"),
    }
    _PROMPT_CACHE[key] = (fp, bundle)
    return bundle


def build_system_and_user_prompts(
    *,
    stage: str,
    scenario: str,
    tags: dict,
    normalized_chat_text: str,
    skill_root: Path | None = None,
) -> tuple[str, str]:
    if skill_root is None:
        skill_root = resolve_skill_root()
    bundle = _load_prompt_bundle(skill_root)
    safety = bundle["safety"]
    evidence = bundle["evidence"]
    rubric = bundle["rubric"]
    lens_evo = bundle["lens_evo"]
    lens_gene = bundle["lens_gene"]
    lens_psy = bundle["lens_psy"]
    lens_lit = bundle["lens_lit"]
    lens_ast = bundle["lens_ast"]
    lens_att = bundle["lens_att"]
    synthesis = bundle["synthesis"]
    reference = bundle["reference"]

    tags_str = ", ".join([f"{k}={v}" for k, v in (tags or {}).items()]) if tags else ""

    system_prompt = (
        "你是「她爱你嘛.skills」的离线分析器。"
        "必须遵守安全边界：若材料疑似涉及监视/骚扰/盗号/未成年人性内容或他人同意缺失，必须拒答并停止分析。\n\n"
        f"{safety}\n\n"
        "你必须输出 Markdown 报告，并严格遵循证据卡片与 synthesis 的结构与约束。"
        "报告需要同时服务两类读者：先给出「普通人一眼能懂」的总结与心动指数，再给出可复核的专业分析；"
        "专业部分仍要有短句解释，避免只有术语堆砌。"
        "全程语气要温柔、以提问与复核为主，不做判决式下结论。\n\n"
        "【术语与禁用表述参考】\n"
        f"{reference}\n"
    )

    user_prompt = (
        "请基于以下输入完成任务（不要省略不确定性与替代解释）。\n\n"
        "【用户输入：关系与场景】\n"
        f"关系阶段：{stage or 'na'}\n"
        f"聊天场景：{scenario or 'na'}\n"
        f"自愿标签：{tags_str or '未提供'}\n\n"
        "【任务 1：证据卡片抽取】\n"
        f"{evidence}\n\n"
        "【任务 2：行为层量表】\n"
        f"{rubric}\n\n"
        "【任务 3：多透镜解读】\n"
        f"{lens_evo}\n\n{lens_gene}\n\n{lens_psy}\n\n{lens_lit}\n\n{lens_ast}\n\n"
        f"{lens_att}\n\n"
        "【任务 4：多透镜合成（必须显式写出冲突调解；若含 L6 可得性须纳入冲突调解）】\n"
        f"{synthesis}\n\n"
        "【原始聊天文本（已尽量归一化）】\n"
        "-----BEGIN CHAT-----\n"
        f"{normalized_chat_text}\n"
        "-----END CHAT-----\n\n"
        "输出要求（顺序很重要，请严格使用下列二级标题）：\n"
        "0) 开头两段必须先写，方便非专业读者理解：\n"
        "## 一眼看懂（人话版）\n"
        "用 4–10 行短句或列表，口语化、少术语；必须交代：大致可能是什么、哪些不能确定、建议怎么看待这份分析。"
        "并至少包含 1 个“温柔可验证问题”（例如：你可以回看聊天里哪一句，来确认/排除某种解释）。\n"
        "## 心动指数\n"
        "用 Markdown 列表写三行（缺一不可）：\n"
        "- **档位**：从「偏低（更像礼貌/距离感）/ 偏谨慎（有好感但不敢松动）/ 信号混在一起（暧昧/边界不清）/ 中等（温柔在意但不稳定）/ 中等偏高（有好感试探）/ 偏高（接近确定但仍需证据）/ 样本不足」中选最贴近的一项（只能选一个）。\n"
        "- **指数**：用 **两个数字的闭区间** 表示心动程度（例如 **52–68**）；"
        "禁止写成单一精确百分比（如 73%）；若样本不足则写「样本不足」并简短说明原因。\n"
        "- **一句话**：用一句完整的人话总结，并在句末用一句小的“你可以怎样确认”的温柔提示收尾（不超过 15 字，避免变成操控话术）。\n"
        "1) 接着写专业部分：必须包含「透镜强度说明」小表（L1–L6）、行为层量表、各透镜小节（含 L6 可得性-多维时须含专业整合 + 给用户的人话要点）、合成（Synthesis）。\n"
        "2) 星座模块仅在用户自愿提供标签且匹配时启用；否则跳过并注明。\n"
        "3) 禁止输出伪精确数字（例如她 87% 爱你）。心动指数已用区间与档位表达，全文保持一致。\n"
    )

    return system_prompt, user_prompt
