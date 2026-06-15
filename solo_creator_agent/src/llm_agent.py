from __future__ import annotations

import json
import os
import base64
import io
import re
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from .schemas import CampaignRecord, ContentRecord, RevenueRecord


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(ROOT / ".env")


def llm_configured() -> bool:
    key = (
        os.getenv("OPENAI_API_KEY", "")
        or os.getenv("OPENAI_API_KEY_BASIC", "")
        or os.getenv("OPENAI_API_KEY_ADVANCED", "")
        or os.getenv("OPENAI_API_KEY_BACKUP_1", "")
        or os.getenv("OPENAI_API_KEY_BACKUP_2", "")
    )
    return bool(key and "your-api-key" not in key)


def _profile_config(profile: str = "basic") -> dict[str, str]:
    suffix = "_ADVANCED" if profile == "advanced" else "_BASIC"
    key = os.getenv(f"OPENAI_API_KEY{suffix}") or os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv(f"OPENAI_BASE_URL{suffix}") or os.getenv("OPENAI_BASE_URL") or ""
    if profile == "advanced":
        model = os.getenv("OPENAI_MODEL_ADVANCED") or "GLM-5-Turbo"
    else:
        model = os.getenv("OPENAI_MODEL_BASIC") or os.getenv("OPENAI_MODEL") or "Qwen3.5-Plus"
    return {"api_key": key, "base_url": base_url, "model": model}


def _profile_configs(profile: str = "basic") -> list[dict[str, str]]:
    base = _profile_config(profile)
    configs: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_config(config: dict[str, str]) -> None:
        key = config.get("api_key", "")
        if not key or key in seen or "your-api-key" in key:
            return
        configs.append(config)
        seen.add(key)

    add_config(base)
    suffix = "_ADVANCED" if profile == "advanced" else "_BASIC"
    for index in range(1, 6):
        scoped_key = os.getenv(f"OPENAI_API_KEY{suffix}_BACKUP_{index}", "")
        generic_key = os.getenv(f"OPENAI_API_KEY_BACKUP_{index}", "")
        for key in [scoped_key, generic_key]:
            if key:
                add_config({**base, "api_key": key})
    return configs


def _client_from_config(config: dict[str, str]) -> OpenAI:
    timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
    return OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"] or None,
        timeout=timeout,
        max_retries=max_retries,
    )


def _extra_body(profile: str = "basic", config: dict[str, str] | None = None) -> dict[str, Any] | None:
    base_url = (config or _profile_config(profile))["base_url"]
    if "aiping.cn" not in base_url:
        return None
    return {
        "enable_thinking": os.getenv("OPENAI_ENABLE_THINKING", "false").lower() == "true",
        "provider": {
            "only": [],
            "order": [],
            "sort": None,
            "input_price_range": [],
            "output_price_range": [],
            "input_length_range": [],
            "output_length_range": [],
            "throughput_range": [],
            "latency_range": [],
        },
    }


def _chat_completion_with_fallback(request: dict[str, Any], profile: str = "basic") -> tuple[str, dict[str, str]]:
    configs = _profile_configs(profile)
    if not configs:
        raise RuntimeError(f"{profile} 模型 API Key 未配置")

    last_error: Exception | None = None
    for index, config in enumerate(configs):
        next_request = dict(request)
        next_request["model"] = config["model"]
        extra = _extra_body(profile, config)
        if extra:
            next_request["extra_body"] = extra
        else:
            next_request.pop("extra_body", None)
        try:
            response = _client_from_config(config).chat.completions.create(**next_request)
            return response.choices[0].message.content or "", config
        except Exception as exc:
            last_error = exc
            if index == len(configs) - 1:
                break
            continue
    assert last_error is not None
    raise last_error


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.head(12).to_dict("records")
    if isinstance(value, pd.Series):
        return value.to_dict()
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "{}").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


def _image_data_url(data: bytes, mime: str) -> str:
    """Compress screenshots before sending them to multimodal APIs."""
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        image.thumbnail((1600, 1600))
        out = io.BytesIO()
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(out, format="JPEG", quality=86, optimize=True)
        data = out.getvalue()
        mime = "image/jpeg"
    except Exception:
        pass
    return f"data:{mime};base64,{base64.b64encode(data).decode('utf-8')}"


def call_llm(system_prompt: str, user_payload: dict[str, Any] | str, language: str = "中文", temperature: float = 0.4, profile: str = "basic") -> str:
    if not llm_configured():
        raise RuntimeError("OPENAI_API_KEY 未配置")

    payload = user_payload if isinstance(user_payload, str) else json.dumps({k: _json_safe(v) for k, v in user_payload.items()}, ensure_ascii=False)
    config = _profile_config(profile)
    request: dict[str, Any] = {
        "model": config["model"],
        "temperature": temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    system_prompt
                    + "\n必须遵守语言要求："
                    + ("全程使用中文，除 CSV、RPM、CTA、Token 等专有名词外不要夹杂英文。" if language == "中文" else "Use English only.")
                ),
            },
            {"role": "user", "content": payload},
        ],
    }
    raw, _ = _chat_completion_with_fallback(request, profile=profile)
    return raw


def generate_ai_business_advice(summary: dict[str, Any], language: str = "中文") -> str:
    prompt = """
你是资深创作者商业增长顾问。请基于结构化经营数据，输出极简、可执行、适合商业产品直接展示的建议。
要求：
1. 只给 3 条今天最该做的动作。
2. 每条不超过 35 个中文字，格式为：动作｜原因｜下一步。
3. 不要虚构数据之外的事实。
4. 样本不足时写“先小范围验证”，不要使用开发、部署、API、低置信度等内部词。
"""
    return call_llm(prompt, summary, language=language, profile="basic")


def interpret_experiment(ab_result: pd.DataFrame, design: dict[str, Any], language: str = "中文") -> str:
    prompt = """
你是增长实验顾问。请把实验结果解释成用户能马上执行的结论。
输出 4 行以内：
1. 结论
2. 是否放大
3. 下一步动作
4. 还要补的数据
不要使用开发、部署、API、低置信度、不声称因果等内部词；需要谨慎时写“先小范围验证”。
"""
    return call_llm(prompt, {"ab_result": ab_result, "experiment_design": design}, language=language, profile="advanced")


def polish_report(markdown_report: str, language: str = "中文") -> str:
    prompt = """
你是创作者经营顾问，请把输入的 Markdown 报告润色成简洁的商业交付版。
要求：
1. 开头给 3 行以内摘要。
2. 行动清单最多 5 条，每条短句。
3. 保留原有数据含义，不编造数字。
4. 不出现开发、部署、API、低置信度、不声称因果等内部词。
"""
    return call_llm(prompt, {"report": markdown_report}, language=language, temperature=0.3, profile="advanced")


ALLOWED_DEFAULTS = {
    "platform": "xiaohongshu",
    "content_type": "tutorial",
    "title_style": "pain_point",
    "revenue_type": "service",
    "status": "pending",
    "campaign_status": "negotiating",
    "payment_status": "unpaid",
    "invoice_status": "pending",
    "report_status": "not_started",
}


def model_status() -> dict[str, Any]:
    basic = _profile_config("basic")
    advanced = _profile_config("advanced")
    return {
        "basic_model": basic["model"],
        "advanced_model": advanced["model"],
        "basic_configured": bool(basic["api_key"]),
        "advanced_configured": bool(advanced["api_key"]),
        "basic_backup_count": max(0, len(_profile_configs("basic")) - 1),
        "advanced_backup_count": max(0, len(_profile_configs("advanced")) - 1),
    }


def _clean_number(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    if isinstance(value, str):
        value = value.replace(",", "").replace("¥", "").strip()
    try:
        return float(value)
    except Exception:
        return default


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _ensure_value(row: dict[str, Any], key: str, default: Any) -> None:
    if key not in row or _is_blank(row.get(key)):
        row[key] = default


def _prepare_record(record: dict[str, Any], target_table: str, index: int) -> dict[str, Any]:
    row = dict(record or {})
    platform = str(row.get("platform") or ALLOWED_DEFAULTS["platform"]).lower().strip()
    platform_aliases = {"小红书": "xiaohongshu", "b站": "bilibili", "哔哩哔哩": "bilibili", "抖音": "douyin", "公众号": "wechat", "视频号": "wechat", "知乎": "zhihu"}
    row["platform"] = platform_aliases.get(platform, platform if platform in {"xiaohongshu", "bilibili", "douyin", "wechat", "zhihu", "youtube", "tiktok", "instagram", "substack", "x"} else ALLOWED_DEFAULTS["platform"])

    if target_table == "contents":
        _ensure_value(row, "content_id", f"U-C{index + 1:04d}")
        _ensure_value(row, "title", "未命名内容")
        _ensure_value(row, "body", "")
        _ensure_value(row, "tags", "")
        _ensure_value(row, "topic", "未分类")
        row["content_type"] = row.get("content_type") if row.get("content_type") in {"tutorial", "story", "review", "listicle", "opinion", "case_study"} else ALLOWED_DEFAULTS["content_type"]
        row["title_style"] = row.get("title_style") if row.get("title_style") in {"pain_point", "tutorial", "number", "story", "contrast", "result_oriented", "question"} else ALLOWED_DEFAULTS["title_style"]
        _ensure_value(row, "cover_style", "default")
        _ensure_value(row, "publish_time", pd.Timestamp.now().isoformat())
        _ensure_value(row, "language", "")
        for key in ["duration_sec", "followers_before", "impressions", "views", "likes", "favorites", "comments", "shares", "new_followers", "consultations", "conversions"]:
            row[key] = int(max(0, _clean_number(row.get(key), 0)))
        row["production_hours"] = max(0, _clean_number(row.get("production_hours"), 0))
        row["completion_rate"] = max(0, _clean_number(row.get("completion_rate"), 0))
        row["revenue"] = max(0, _clean_number(row.get("revenue"), 0))
        row["cost"] = max(0, _clean_number(row.get("cost"), 0))
        row["ad_spend"] = max(0, _clean_number(row.get("ad_spend"), 0))
        row["is_sponsored"] = bool(row.get("is_sponsored", False))
    elif target_table == "revenues":
        _ensure_value(row, "revenue_id", f"U-R{index + 1:04d}")
        _ensure_value(row, "date", pd.Timestamp.now().date().isoformat())
        row["amount"] = max(0, _clean_number(row.get("amount"), 0))
        row["revenue_type"] = row.get("revenue_type") if row.get("revenue_type") in {"brand_ads", "platform_share", "course", "consulting", "membership", "affiliate", "reward", "service"} else ALLOWED_DEFAULTS["revenue_type"]
        row["status"] = row.get("status") if row.get("status") in {"received", "pending"} else "pending"
        _ensure_value(row, "content_id", "")
        _ensure_value(row, "client_name", "")
        _ensure_value(row, "note", "")
    elif target_table == "campaigns":
        _ensure_value(row, "campaign_id", f"U-B{index + 1:04d}")
        _ensure_value(row, "brand_name", "未命名品牌")
        _ensure_value(row, "campaign_name", row.get("deliverables") or "商务合作")
        _ensure_value(row, "deliverables", "待确认交付物")
        row["price"] = max(0, _clean_number(row.get("price"), 0))
        _ensure_value(row, "deadline", pd.Timestamp.now().date().isoformat())
        row["status"] = row.get("status") if row.get("status") in {"negotiating", "confirmed", "scripting", "reviewing", "published", "reporting", "completed"} else ALLOWED_DEFAULTS["campaign_status"]
        row["payment_status"] = row.get("payment_status") if row.get("payment_status") in {"unpaid", "deposit_received", "fully_paid", "overdue"} else ALLOWED_DEFAULTS["payment_status"]
        row["invoice_status"] = row.get("invoice_status") if row.get("invoice_status") in {"not_needed", "pending", "issued"} else ALLOWED_DEFAULTS["invoice_status"]
        row["revision_count"] = int(max(0, _clean_number(row.get("revision_count"), 0)))
        row["report_status"] = row.get("report_status") if row.get("report_status") in {"not_started", "generated", "sent"} else ALLOWED_DEFAULTS["report_status"]
        _ensure_value(row, "related_content_id", "")
    return row


def validate_records(records: list[dict[str, Any]], target_table: str) -> dict[str, Any]:
    model = {"contents": ContentRecord, "revenues": RevenueRecord, "campaigns": CampaignRecord}[target_table]
    valid = []
    errors = []
    for index, record in enumerate(records or []):
        prepared = _prepare_record(record, target_table, index)
        try:
            valid.append(model.model_validate(prepared).model_dump(mode="json"))
        except ValidationError as exc:
            errors.append({"index": index, "errors": exc.errors(), "raw": record})
    return {
        "records": valid,
        "errors": errors,
        "valid_count": len(valid),
        "error_count": len(errors),
    }


def extract_records_from_uploads(text: str, files: list[Any], target_table: str, language: str = "中文") -> dict[str, Any]:
    if not llm_configured():
        raise RuntimeError("OPENAI_API_KEY 未配置")

    schema_hint = {
        "contents": "content_id,title,platform,body,tags,topic,content_type,publish_time,language,title_style,cover_style,duration_sec,production_hours,followers_before,impressions,views,likes,favorites,comments,shares,completion_rate,new_followers,consultations,conversions,revenue,cost,ad_spend,is_sponsored",
        "revenues": "revenue_id,date,amount,revenue_type,platform,content_id,client_name,status,note",
        "campaigns": "campaign_id,brand_name,campaign_name,platform,deliverables,price,deadline,status,payment_status,invoice_status,revision_count,report_status,related_content_id",
    }.get(target_table, "contents")

    content_parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "请从用户上传的截图和文字中抽取结构化数据。"
                f"目标表：{target_table}。字段：{schema_hint}。"
                "只返回 JSON，格式为 {\"records\": [...], \"tasks\": [...], \"notes\": \"...\"}。"
                "如果用户输入明显是待办、提醒、会议、汇报、截止事项，请放入 tasks，不要硬塞进 records。"
                "tasks 字段为 title, detail, due_at, priority, source。priority 可用 high, medium, low。"
                "无法确定的字段请合理填默认值或空字符串，不要编造明显不存在的信息。"
                "平台名统一使用 xiaohongshu,bilibili,douyin,wechat,zhihu,youtube,tiktok,instagram,substack,x。"
                "数值字段必须是数字。日期字段使用 YYYY-MM-DD 或 ISO 时间。"
                f"\n用户补充文字：{text or '无'}"
            ),
        }
    ]

    has_images = False
    for file in files[:6]:
        data = file.getvalue()
        mime = getattr(file, "type", None) or "image/png"
        if mime.startswith("image/"):
            has_images = True
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": _image_data_url(data, mime)},
            })
        else:
            try:
                file_text = data.decode("utf-8", errors="ignore")[:8000]
            except Exception:
                file_text = f"文件名：{getattr(file, 'name', 'unknown')}，无法直接解码。"
            content_parts.append({"type": "text", "text": file_text})

    # Qwen3.5-Plus is the configured low-cost / long-context model and supports
    # the user's image-reading workflow. Some providers reject vision requests
    # when routed to text-only models or when response_format is forced.
    profile = "basic"
    config = _profile_config(profile)
    request: dict[str, Any] = {
        "model": config["model"],
        "temperature": 0.1,
        "messages": [
            {
                "role": "system",
                "content": "你是创作者经营数据录入助手，负责把截图、账单、后台数据、聊天文字整理成可分析的 CSV 表记录。只返回 JSON。",
            },
            {"role": "user", "content": content_parts},
        ],
    }
    if not has_images and os.getenv("OPENAI_RESPONSE_FORMAT", "json_object") != "none":
        request["response_format"] = {"type": "json_object"}
    try:
        raw, used_config = _chat_completion_with_fallback(request, profile=profile)
    except Exception as exc:
        if has_images:
            raise RuntimeError("图片暂时未能读取。请换一张更清晰的截图，或把关键文字粘贴到文本框。") from exc
        raise
    extracted = _extract_json_object(raw)
    validation = validate_records(extracted.get("records", []), target_table)
    notes = extracted.get("notes", "")
    if validation["error_count"]:
        notes = f"{notes}；有 {validation['error_count']} 条记录未通过字段校验，已跳过。".strip("；")
    return {
        "records": validation["records"],
        "tasks": extracted.get("tasks", []),
        "notes": notes,
        "validation": validation,
        "model_profile": profile,
        "model": used_config["model"],
    }
