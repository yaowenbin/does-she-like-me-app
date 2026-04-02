from __future__ import annotations

import os
from pathlib import Path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _find_default_skill_root() -> Path | None:
    """
    Locate `Day7/does-she-like-me/skills/does-she-like-me` relative to this file.
    """
    here = Path(__file__).resolve()
    # .../does-she-like-me-web/backend/app/prompt_builder.py
    # parents[3] should be .../Day7
    day7_dir = here.parents[3]
    candidate = day7_dir / "does-she-like-me" / "skills" / "does-she-like-me"
    if (candidate / "SKILL.md").is_file():
        return candidate
    return None


def build_system_and_user_prompts(
    *,
    stage: str,
    scenario: str,
    tags: dict,
    normalized_chat_text: str,
    skill_root: Path | None = None,
) -> tuple[str, str]:
    if skill_root is None:
        env = (os.getenv("DOES_SHE_LIKE_ME_SKILL_ROOT") or "").strip()
        if env:
            skill_root = Path(env)
        else:
            skill_root = _find_default_skill_root()

    if not skill_root:
        raise RuntimeError(
            "Cannot locate skill templates. Set DOES_SHE_LIKE_ME_SKILL_ROOT env var or place templates under Day7/does-she-like-me/skills/does-she-like-me."
        )

    # Load prompt fragments (keep it simple: we rely on the skill templates' wording).
    safety = _read_text(skill_root / "prompts" / "safety_refusal.md")
    evidence = _read_text(skill_root / "prompts" / "analyze_segments.md")
    rubric = _read_text(skill_root / "prompts" / "score_rubric.md")
    lens_evo = _read_text(skill_root / "prompts" / "lens_evolution.md")
    lens_gene = _read_text(skill_root / "prompts" / "lens_gene_rhetoric.md")
    lens_psy = _read_text(skill_root / "prompts" / "lens_psychology.md")
    lens_lit = _read_text(skill_root / "prompts" / "lens_literature.md")
    lens_ast = _read_text(skill_root / "prompts" / "lens_astrology.md")
    synthesis = _read_text(skill_root / "prompts" / "synthesis.md")
    reference = _read_text(skill_root / "reference.md")

    tags_str = ", ".join([f"{k}={v}" for k, v in (tags or {}).items()]) if tags else ""

    system_prompt = (
        "你是「她爱你嘛.skills」的离线分析器。"
        "必须遵守安全边界：若材料疑似涉及监视/骚扰/盗号/未成年人性内容或他人同意缺失，必须拒答并停止分析。\n\n"
        f"{safety}\n\n"
        "你必须输出 Markdown 报告，并严格遵循证据卡片与 synthesis 的结构与约束。"
        "\n\n【术语与禁用表述参考】\n"
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
        "【任务 4：多透镜合成（必须显式写出冲突调解）】\n"
        f"{synthesis}\n\n"
        "【原始聊天文本（已尽量归一化）】\n"
        "-----BEGIN CHAT-----\n"
        f"{normalized_chat_text}\n"
        "-----END CHAT-----\n\n"
        "输出要求：\n"
        "1) 顶层必须包含「透镜强度说明」小表、行为层量表、各透镜小节、合成（Synthesis）。\n"
        "2) 星座模块仅在用户自愿提供标签且匹配时启用；否则跳过并注明。\n"
        "3) 禁止输出伪精确数字（例如她 87% 爱你）。使用区间/等级（偏低/不明/中等偏高/样本不足）。\n"
    )

    return system_prompt, user_prompt

