"""
「她爱你嘛」Skill 模板包：发现、缓存与按需从官方仓库安装。

优先级：
1) 环境变量 DOES_SHE_LIKE_ME_SKILL_ROOT（显式路径）
2) 开发态：与本仓库并排的 monorepo 路径（code/Day7/...）
3) 数据目录下缓存 DATA_DIR/.skills/does-she-like-me
4) 若允许自动安装：git shallow clone 官方仓库并复制 skills/does-she-like-me 到缓存

命令行：在 backend 目录执行
  python -m app.skills_bundle install
  python -m app.skills_bundle status
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

# 与开源仓库 README 一致；可用 DOES_SHE_LIKE_ME_SKILLS_GIT_URL 覆盖（含自建镜像）。
DEFAULT_SKILLS_GIT_URL = "https://github.com/yaowenbin/does-she-like-me.git"
SKILL_DIR_IN_REPO = Path("skills") / "does-she-like-me"

_install_lock = threading.Lock()

# 用于校验「可生成报告」的最小文件集（与 prompt_builder 读取一致）
_REQUIRED_REL_PATHS: tuple[str, ...] = (
    "SKILL.md",
    "reference.md",
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
)


def default_data_dir() -> Path:
    return Path(os.getenv("DATA_DIR") or (Path(__file__).resolve().parents[2] / "data"))


def skill_cache_dir(data_dir: Path | None = None) -> Path:
    base = data_dir if data_dir is not None else default_data_dir()
    return (base / ".skills" / "does-she-like-me").resolve()


def is_complete_bundle(root: Path) -> bool:
    if not root.is_dir():
        return False
    return all((root / rel).is_file() for rel in _REQUIRED_REL_PATHS)


def _find_monorepo_skill_root() -> Path | None:
    here = Path(__file__).resolve()
    rel_candidates = (
        Path("code") / "Day7" / "does-she-like-me" / SKILL_DIR_IN_REPO,
        Path("does-she-like-me") / SKILL_DIR_IN_REPO,
        Path("skills") / "does-she-like-me",
    )
    seen: set[Path] = set()
    for parent in here.parents:
        for rel in rel_candidates:
            candidate = (parent / rel).resolve()
            if candidate in seen:
                continue
            seen.add(candidate)
            if is_complete_bundle(candidate):
                return candidate
    return None


def _git_url() -> str:
    return (os.getenv("DOES_SHE_LIKE_ME_SKILLS_GIT_URL") or "").strip() or DEFAULT_SKILLS_GIT_URL


def _auto_install_enabled() -> bool:
    v = (os.getenv("DOES_SHE_LIKE_ME_SKILLS_AUTO_INSTALL") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def install_skill_bundle_from_git(
    dest: Path,
    *,
    git_url: str | None = None,
) -> Path:
    """
    将远程仓库中的 skills/does-she-like-me 安装到 dest（覆盖写入）。
    需要本机 PATH 中有 git。
    """
    url = git_url or _git_url()
    if shutil.which("git") is None:
        raise RuntimeError(
            "未检测到 git 命令。请先安装 Git 并加入 PATH，"
            "或手动下载技能包后设置 DOES_SHE_LIKE_ME_SKILL_ROOT。"
        )

    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dslm-skills-") as td:
        clone_root = Path(td) / "repo"
        r = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(clone_root)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            raise RuntimeError(
                f"git clone 失败（url={url}）。可检查网络、代理或改用镜像环境变量 DOES_SHE_LIKE_ME_SKILLS_GIT_URL。"
                + (f"\n{err}" if err else "")
            )

        src = clone_root / SKILL_DIR_IN_REPO
        if not src.is_dir():
            raise RuntimeError(
                f"仓库中未找到 {SKILL_DIR_IN_REPO.as_posix()}，请确认 DOES_SHE_LIKE_ME_SKILLS_GIT_URL 指向正确的 does-she-like-me 仓库。"
            )
        if not is_complete_bundle(src):
            raise RuntimeError("克隆到的技能包不完整，请向仓库维护者反馈。")

        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

    if not is_complete_bundle(dest):
        raise RuntimeError("安装后校验失败，请重试或手动指定 DOES_SHE_LIKE_ME_SKILL_ROOT。")
    return dest


def resolve_skill_root(
    *,
    data_dir: Path | None = None,
    allow_auto_install: bool = True,
) -> Path:
    """
    解析最终使用的技能包根目录（含 SKILL.md、prompts/）。
    """
    env = (os.getenv("DOES_SHE_LIKE_ME_SKILL_ROOT") or "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if is_complete_bundle(p):
            return p
        raise RuntimeError(
            f"DOES_SHE_LIKE_ME_SKILL_ROOT 指向的目录不完整或不存在：{p}"
        )

    mono = _find_monorepo_skill_root()
    if mono is not None:
        return mono

    cache = skill_cache_dir(data_dir)
    if is_complete_bundle(cache):
        return cache

    if allow_auto_install and _auto_install_enabled():
        with _install_lock:
            if is_complete_bundle(cache):
                return cache
            return install_skill_bundle_from_git(cache)

    raise RuntimeError(
        "未安装「她爱你嘛」技能模板。请在 backend 目录执行：python -m app.skills_bundle install\n"
        "或设置 DOES_SHE_LIKE_ME_SKILL_ROOT；离线环境可设置 DOES_SHE_LIKE_ME_SKILLS_AUTO_INSTALL=0 后手动拷贝技能目录。"
    )


def _cli_install(data_dir: Path | None, git_url: str | None) -> int:
    dest = skill_cache_dir(data_dir)
    install_skill_bundle_from_git(dest, git_url=git_url)
    print(f"已安装技能包到：{dest}")
    return 0


def _cli_status(data_dir: Path | None) -> int:
    dd = data_dir or default_data_dir()
    print(f"DATA_DIR: {dd.resolve()}")
    print(f"缓存路径: {skill_cache_dir(dd)}")

    env = (os.getenv("DOES_SHE_LIKE_ME_SKILL_ROOT") or "").strip()
    if env:
        print(f"DOES_SHE_LIKE_ME_SKILL_ROOT: {env}")

    try:
        root = resolve_skill_root(data_dir=dd, allow_auto_install=False)
        print(f"当前解析结果: {root}")
        print("状态: 可用（未触发自动安装）")
    except RuntimeError as e:
        print(f"状态: 不可用 — {e}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="她爱你嘛 skills 安装与状态")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("install", help="从 Git 拉取并安装到 DATA_DIR/.skills/")
    pi.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="覆盖 DATA_DIR（默认读环境变量或 backend/data）",
    )
    pi.add_argument(
        "--url",
        default=None,
        help="覆盖仓库 URL（默认官方或环境变量 DOES_SHE_LIKE_ME_SKILLS_GIT_URL）",
    )

    ps = sub.add_parser("status", help="查看解析路径与是否就绪（不自动下载）")
    ps.add_argument("--data-dir", type=Path, default=None)

    args = p.parse_args(argv)
    if args.cmd == "install":
        return _cli_install(args.data_dir, args.url)
    if args.cmd == "status":
        return _cli_status(args.data_dir)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
