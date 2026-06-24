import json
import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """配置相关异常（文件损坏、读写失败等）"""
    pass


class Settings(BaseModel):
    """配置数据模型，字段都有默认值"""
    novel_dir: str = "."
    ai_provider: str = "deepseek"
    api_base: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    language: str = "zh"
    auto_scan_interval: int = 3600
    query_cheap_base: str = "http://localhost:11434/v1"
    query_cheap_model: str = "qwen2.5:7b"

    @property
    def masked_api_key(self) -> str:
        return self.api_key[:6] + "****" + self.api_key[-2:]

DEFAULT_CONFIG = {
    "novel_dir": ".",
    "ai_provider": "deepseek",
    "api_base": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-chat",
    "language": "zh",
    "auto_scan_interval": 3600,
    "query_cheap_base": "http://localhost:11434/v1",
    "query_cheap_model": "qwen2.5:7b",
}

def save_config(settings: Settings, config_path: Path) -> None:
    """将配置对象持久化到 JSON 文件"""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        settings.model_dump_json(indent=2,exclude_none=True),
        encoding="utf-8",
    )
    logger.info(f"配置已保存到 {config_path}")

def init_default_config(config_path: Path) -> Settings:
    """创建默认配置文件并写入磁盘"""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    settings = Settings(**DEFAULT_CONFIG)
    save_config(settings, config_path )
    logger.info(f"默认配置已创建： {config_path}")
    return settings


def load_config(config_path: Path) -> Settings:
    """从json文件加载配置，缺失字段用默认值填充"""
    if not config_path.exists():
        return init_default_config(config_path)

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"配置文件损坏，不是合法的json： {config_path} \n {e}"
        ) from e
    except FileNotFoundError:
        return init_default_config(config_path)

    return Settings(**data)


























