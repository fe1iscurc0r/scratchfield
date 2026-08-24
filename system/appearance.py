"""
外观定制模块 - 主题、配色、样式管理
"""
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# MEDIUM CSS注入防护: 颜色值正则（hex/rgb/rgba/命名颜色）
_CSS_COLOR_RE = re.compile(
    r'^(#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})|'
    r'rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}(\s*,\s*[\d.]+\s*)?\)|'
    r'[a-zA-Z][a-zA-Z0-9]{2,20})$'
)

# MEDIUM CSS注入防护: CSS值中不允许的注入字符
_CSS_INJECT_RE = re.compile(r'[;{}()<>`$\\]')

# MEDIUM CSS注入防护: 允许的字体/尺寸字符
_CSS_SAFE_RE = re.compile(r'^[a-zA-Z0-9\s,\'\"\-_.]+$')


def _is_valid_css_color(value: str) -> bool:
    """校验是否为合法 CSS 颜色值"""
    return bool(_CSS_COLOR_RE.match(value.strip()))


def _sanitize_css_value(value: str, max_len: int = 200) -> str:
    """清洗 CSS 值，移除注入字符"""
    v = str(value).strip()
    # 移除所有 CSS 注入危险字符
    v = _CSS_INJECT_RE.sub('', v)
    # 截断超长值
    if len(v) > max_len:
        v = v[:max_len]
    return v


def _is_safe_css_string(value: str) -> bool:
    """校验字符串是否只包含允许的 CSS 安全字符"""
    return bool(_CSS_SAFE_RE.match(str(value)))

logger = logging.getLogger(__name__)

# HIGH-5: 单例线程锁
_appearance_manager: Optional['AppearanceManager'] = None
_appearance_lock = threading.Lock()


class ThemeColors(BaseModel):
    """主题配色"""
    primary: str = "#1890ff"
    secondary: str = "#722ed1"
    accent: str = "#13c2c2"
    background: str = "#ffffff"
    surface: str = "#f5f5f5"
    text_primary: str = "#1f1f1f"
    text_secondary: str = "#666666"
    border: str = "#e8e8e8"


class DialogStyle(BaseModel):
    """对话框样式"""
    border_radius: str = "12px"
    border_width: int = 1
    shadow: str = "0 2px 8px rgba(0,0,0,0.08)"
    padding: str = "16px"
    max_width: str = "600px"
    animation_duration: str = "0.3s"


class AppearanceConfig(BaseModel):
    """外观配置"""
    theme_name: str = "research_blue"
    colors: ThemeColors = Field(default_factory=ThemeColors)
    dialog_style: DialogStyle = Field(default_factory=DialogStyle)
    avatar: str = ""
    font_family: str = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    font_size_base: str = "14px"
    density: str = "normal"  # compact, normal, comfortable


class AppearanceManager:
    """外观管理器"""
    
    def __init__(self):
        self._config: AppearanceConfig | None = None
        self._themes: dict[str, dict[str, Any]] = {}
        self._load_builtin_themes()
        self._load_config()
    
    def _load_builtin_themes(self):
        """加载内置主题"""
        self._themes = {
            "research_blue": {
                "name": "科研蓝",
                "description": "专业的科研蓝色调",
                "colors": ThemeColors(
                    primary="#1890ff",
                    secondary="#722ed1",
                    accent="#13c2c2",
                    background="#ffffff",
                    surface="#f5f7fa",
                    text_primary="#1f1f1f",
                    text_secondary="#666666",
                    border="#e8e8e8",
                ).model_dump(),
            },
            "light": {
                "name": "浅色模式",
                "description": "简洁明亮的浅色主题",
                "colors": ThemeColors(
                    primary="#409eff",
                    secondary="#a78bfa",
                    accent="#34d399",
                    background="#fafafa",
                    surface="#ffffff",
                    text_primary="#213547",
                    text_secondary="#6b7280",
                    border="#e5e7eb",
                ).model_dump(),
            },
            "dark": {
                "name": "深夜模式",
                "description": "护眼的深色主题",
                "colors": ThemeColors(
                    primary="#40a9ff",
                    secondary="#9254de",
                    accent="#36cfc9",
                    background="#141414",
                    surface="#1f1f1f",
                    text_primary="#e6e6e6",
                    text_secondary="#999999",
                    border="#303030",
                ).model_dump(),
            },
            "forest": {
                "name": "森林绿",
                "description": "自然清新的绿色调",
                "colors": ThemeColors(
                    primary="#52c41a",
                    secondary="#13c2c2",
                    accent="#faad14",
                    background="#ffffff",
                    surface="#f6ffed",
                    text_primary="#1f1f1f",
                    text_secondary="#595959",
                    border="#d9f7be",
                ).model_dump(),
            },
            "sunset": {
                "name": "夕阳橙",
                "description": "温暖活力的橙色调",
                "colors": ThemeColors(
                    primary="#fa541c",
                    secondary="#eb2f96",
                    accent="#faad14",
                    background="#ffffff",
                    surface="#fff7e6",
                    text_primary="#1f1f1f",
                    text_secondary="#595959",
                    border="#ffd591",
                ).model_dump(),
            },
        }
    
    def _load_config(self):
        """加载配置"""
        try:
            from system.config import get_data_dir
            config_path = get_data_dir() / "appearance.json"
            
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._config = AppearanceConfig(**data)
                logger.info(f"外观配置加载成功: {config_path}")
            else:
                self._config = AppearanceConfig()
                self._apply_theme("research_blue")
        except Exception as e:
            logger.error(f"加载外观配置失败: {e}")
            self._config = AppearanceConfig()
    
    def _apply_theme(self, theme_name: str):
        """应用主题配色"""
        if theme_name in self._themes and self._config:
            theme = self._themes[theme_name]
            colors_data = theme["colors"]
            self._config.colors = ThemeColors(**colors_data)
            self._config.theme_name = theme_name
    
    def get_config(self) -> AppearanceConfig:
        """获取当前外观配置"""
        return self._config
    
    def set_theme(self, theme_name: str) -> bool:
        """切换主题"""
        if theme_name not in self._themes:
            logger.error(f"主题 '{theme_name}' 不存在")
            return False
        self._apply_theme(theme_name)
        self.save_config()
        logger.info(f"切换主题: {theme_name}")
        return True
    
    def list_themes(self) -> list[dict[str, Any]]:
        """列出所有主题"""
        result = []
        for name, theme in self._themes.items():
            result.append({
                "name": name,
                "display_name": theme["name"],
                "description": theme["description"],
                "is_active": name == self._config.theme_name,
                "preview_colors": {
                    "primary": theme["colors"]["primary"],
                    "background": theme["colors"]["background"],
                },
            })
        return result
    
    def set_colors(self, **kwargs) -> bool:
        """自定义配色"""
        try:
            colors = self._config.colors
            for key, value in kwargs.items():
                if hasattr(colors, key) and isinstance(value, str):
                    # MEDIUM CSS注入防护: 校验颜色值
                    if not _is_valid_css_color(value):
                        logger.warning(f"非法颜色值被拦截: {key}={value}")
                        continue
                    setattr(colors, key, value)
            self.save_config()
            return True
        except Exception as e:
            logger.error(f"设置配色失败: {e}")
            return False
    
    def set_dialog_style(self, **kwargs) -> bool:
        """设置对话框样式"""
        try:
            style = self._config.dialog_style
            for key, value in kwargs.items():
                if hasattr(style, key) and isinstance(value, str):
                    # MEDIUM CSS注入防护: 清洗CSS值
                    safe_val = _sanitize_css_value(value)
                    setattr(style, key, safe_val)
            self.save_config()
            return True
        except Exception as e:
            logger.error(f"设置对话框样式失败: {e}")
            return False
    
    def set_avatar(self, avatar_path: str) -> bool:
        """设置头像"""
        # MEDIUM CSS注入防护: 限制头像路径字符
        safe_path = _sanitize_css_value(avatar_path, max_len=500)
        self._config.avatar = safe_path
        self.save_config()
        return True
    
    def set_font(self, font_family: str = None, font_size: str = None) -> bool:
        """设置字体"""
        if font_family:
            # MEDIUM CSS注入防护: 字体名清洗
            self._config.font_family = _sanitize_css_value(font_family, max_len=200)
        if font_size:
            # MEDIUM CSS注入防护: 字体大小只允许数字+单位
            safe_size = _sanitize_css_value(font_size, max_len=20)
            if safe_size and re.match(r'^[\d.]+(px|em|rem|%)?$', safe_size):
                self._config.font_size_base = safe_size
        self.save_config()
        return True
    
    def set_density(self, density: str) -> bool:
        """设置密度"""
        if density in ("compact", "normal", "comfortable"):
            self._config.density = density
            self.save_config()
            return True
        return False
    
    def generate_css_variables(self) -> str:
        """生成 CSS 变量"""
        config = self._config
        colors = config.colors
        style = config.dialog_style
        
        css = f"""/* 陆墨外观 CSS 变量 - 主题: {config.theme_name} */
:root {{
  /* 主题配色 */
  --lm-color-primary: {colors.primary};
  --lm-color-secondary: {colors.secondary};
  --lm-color-accent: {colors.accent};
  --lm-color-background: {colors.background};
  --lm-color-surface: {colors.surface};
  --lm-color-text-primary: {colors.text_primary};
  --lm-color-text-secondary: {colors.text_secondary};
  --lm-color-border: {colors.border};
  
  /* 对话框样式 */
  --lm-dialog-border-radius: {style.border_radius};
  --lm-dialog-border-width: {style.border_width}px;
  --lm-dialog-shadow: {style.shadow};
  --lm-dialog-padding: {style.padding};
  --lm-dialog-max-width: {style.max_width};
  --lm-dialog-animation: {style.animation_duration};
  
  /* 字体 */
  --lm-font-family: {config.font_family};
  --lm-font-size-base: {config.font_size_base};
  
  /* 密度 */
  --lm-density: {config.density};
}}
"""
        return css
    
    def get_frontend_config(self) -> dict[str, Any]:
        """获取前端配置"""
        config = self._config
        return {
            "theme": {
                "name": config.theme_name,
                "colors": config.colors.model_dump(),
            },
            "dialog": config.dialog_style.model_dump(),
            "avatar": config.avatar,
            "typography": {
                "fontFamily": config.font_family,
                "fontSizeBase": config.font_size_base,
            },
            "density": config.density,
            "cssVariables": self.generate_css_variables(),
        }
    
    def save_config(self) -> bool:
        """保存配置"""
        try:
            from system.config import get_data_dir
            config_path = get_data_dir() / "appearance.json"
            
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self._config.model_dump(), f, ensure_ascii=False, indent=2)
            
            logger.info(f"外观配置保存成功: {config_path}")
            return True
        except Exception as e:
            logger.error(f"保存外观配置失败: {e}")
            return False


def get_appearance_manager() -> AppearanceManager:
    """获取全局外观管理器（线程安全单例）"""
    global _appearance_manager
    # HIGH-5: 双检锁模式
    if _appearance_manager is None:
        with _appearance_lock:
            if _appearance_manager is None:
                _appearance_manager = AppearanceManager()
    return _appearance_manager
