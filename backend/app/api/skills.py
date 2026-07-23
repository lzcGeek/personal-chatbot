import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request, UploadFile, status

from app.schemas.skill import SkillCreate


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills(request: Request) -> dict[str, list[dict]]:
    return {"skills": request.app.state.skill_loader.as_dicts()}


@router.post("/{name}/enable")
async def enable_skill(name: str, request: Request) -> dict[str, object]:
    if not request.app.state.skill_loader.set_enabled(name, True):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"name": name, "enabled": True}


@router.post("/{name}/disable")
async def disable_skill(name: str, request: Request) -> dict[str, object]:
    if not request.app.state.skill_loader.set_enabled(name, False):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"name": name, "enabled": False}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_skill(payload: SkillCreate, request: Request) -> dict[str, object]:
    name = payload.name.strip()
    loader = request.app.state.skill_loader
    target_dir = loader.root_path / name
    if target_dir.exists():
        raise HTTPException(status_code=409, detail=f"Skill '{name}' already exists")
    try:
        target_dir.mkdir(parents=True)
        frontmatter = f"---\nname: {name}\ndescription: {payload.description.strip()}\n---\n"
        (target_dir / "SKILL.md").write_text(
            frontmatter + "\n" + payload.content.strip() + "\n", encoding="utf-8"
        )
    except OSError as exc:
        logger.error("Failed to create skill %s: %s", name, exc)
        raise HTTPException(status_code=500, detail="Failed to create skill file") from exc
    return {
        "name": name,
        "description": payload.description.strip(),
        "path": str(target_dir / "SKILL.md"),
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_skill(file: UploadFile, request: Request) -> dict[str, object]:
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=422, detail="只支持 .md 格式的 Skill 文件")
    raw = (await file.read()).decode("utf-8")
    if not raw.startswith("---\n"):
        raise HTTPException(status_code=422, detail="文件缺少 YAML frontmatter（以 --- 开头）")
    try:
        _, frontmatter_text, body = raw.split("---", 2)
    except ValueError:
        raise HTTPException(status_code=422, detail="YAML frontmatter 格式不正确")
    try:
        metadata = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"YAML 解析失败: {exc}") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=422, detail="frontmatter 必须是 YAML 映射")
    name = metadata.get("name")
    description = metadata.get("description", "")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=422, detail="frontmatter 中缺少有效的 name 字段")
    if not body.strip() and not description.strip():
        raise HTTPException(status_code=422, detail="Skill 内容和描述不能同时为空")

    loader = request.app.state.skill_loader
    target_dir = loader.root_path / name.strip()
    if target_dir.exists():
        raise HTTPException(status_code=409, detail=f"Skill '{name.strip()}' 已存在")
    try:
        target_dir.mkdir(parents=True)
        (target_dir / "SKILL.md").write_text(raw, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write uploaded skill %s: %s", name, exc)
        raise HTTPException(status_code=500, detail="写入 Skill 文件失败") from exc
    return {
        "name": name.strip(),
        "description": str(description).strip(),
        "path": str(target_dir / "SKILL.md"),
    }


@router.post("/reload")
async def reload_skills(request: Request) -> dict[str, object]:
    skills = request.app.state.skill_loader.load()
    return {
        "count": len(skills),
        "skills": request.app.state.skill_loader.as_dicts(),
    }
