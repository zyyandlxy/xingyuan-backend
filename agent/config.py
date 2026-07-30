"""
配置管理模块
从环境变量加载所有配置，提供类型安全的配置访问
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置，自动从 .env / 环境变量加载"""

    # --- 智谱 AI ---
    zhipuai_api_key: str = Field(
        default="",
        description="智谱 AI API Key，必填",
    )
    zhipuai_model: str = Field(
        default="glm-4-flash",
        description="默认模型名称",
    )
    zhipuai_max_tokens: int = Field(
        default=4096,
        ge=1,
        le=128000,
        description="单次最大输出 token 数",
    )
    zhipuai_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="采样温度",
    )

    # --- 服务认证 ---
    service_api_key: str = Field(
        default="",
        description="保护服务的 API Key，留空则不启用",
    )

    # --- 服务配置 ---
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = Field(default=False)

    # --- CORS ---
    cors_origins: str = Field(
        default="*",
        description="逗号分隔的允许来源，* 表示全部",
    )

    # --- 限流 ---
    rate_limit_per_minute: int = Field(
        default=60,
        ge=0,
        description="每 IP 每分钟最大请求数，0 不限制",
    )

    # --- 存储 ---
    database_path: str = Field(
        default="data/conversations.db",
        description="SQLite 数据库文件路径",
    )

    # --- 日志 ---
    log_level: str = Field(
        default="INFO",
        description="日志级别: DEBUG/INFO/WARNING/ERROR",
    )
    log_file: str = Field(
        default="logs/agent.log",
        description="日志文件路径",
    )

    # --- 工具调用 ---
    max_tool_rounds: int = Field(
        default=10,
        ge=1,
        le=50,
        description="工具调用最大轮次，防止死循环",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def cors_origin_list(self) -> list[str]:
        """解析 CORS 来源列表"""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_auth_enabled(self) -> bool:
        """是否启用了服务级 API Key 认证"""
        return bool(self.service_api_key)


# 全局单例
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例（懒加载）"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """强制重新加载配置"""
    global _settings
    _settings = Settings()
    return _settings
