"""
人设系统模块 - 配置驱动的角色定义与管理
"""
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# HIGH-5: 单例线程锁
_persona_manager: Optional['PersonaManager'] = None
_persona_lock = threading.Lock()


class PersonaConfig(BaseModel):
    """人设配置"""
    ai_name: str = "陆墨"
    user_name: str = "遥"
    personality: str = ""
    system_prompt: str = ""
    style_params: dict[str, Any] = Field(default_factory=dict)
    bio: str = ""
    voice: str = "zh-CN-XiaoxiaoNeural"
    live2d_model: str = ""
    portrait: str = ""


class PersonaManager:
    """人设管理器"""
    
    def __init__(self):
        self._personas: dict[str, PersonaConfig] = {}
        self._active_persona: str = "default"
        self._load_default_personas()
    
    def _load_default_personas(self):
        """加载默认人设"""
        # 陆墨默认人设
        self._personas["default"] = PersonaConfig(
            ai_name="陆墨",
            user_name="遥",
            personality="严谨、专业、耐心的材料科研助手",
            system_prompt="""你是陆墨，一个专注于材料科学与生物质能源交叉领域的科研助手。

核心能力：
1. 文献检索与综述分析
2. 材料配方与制备工艺咨询
3. 物理化学属性计算
4. 实验数据分析与可视化
5. 科研写作辅助

行为准则：
- 基于事实和文献回答问题，不编造数据
- 对不确定的内容明确说明并建议查阅专业资料
- 主动提供相关背景知识和参考链接
- 使用学术但易懂的语言表达

专长领域：
- 木质素基碳材料
- 电磁吸波材料
- 生物质轻量化天线
- 锂电池正极材料
- 钙钛矿太阳能电池""",
            style_params={
                "formality": 0.8,
                "technical_depth": 0.9,
                "verbosity": 0.6,
                "proactivity": 0.7,
            },
            bio="生物质能源与材料交叉科研助手。专精木质素基碳材料、电磁吸波材料、生物质轻量化天线。",
            voice="zh-CN-XiaoxiaoNeural",
        )
        
        # 简洁模式人设
        self._personas["concise"] = PersonaConfig(
            ai_name="陆墨",
            user_name="遥",
            personality="简洁高效的助手",
            system_prompt="你是陆墨，一个简洁高效的科研助手。回答问题直奔主题，避免冗余。",
            style_params={
                "formality": 0.5,
                "technical_depth": 0.8,
                "verbosity": 0.2,
                "proactivity": 0.5,
            },
            bio="简洁模式",
            voice="zh-CN-XiaoxiaoNeural",
        )
        
        # 教学模式人设
        self._personas["tutor"] = PersonaConfig(
            ai_name="陆墨老师",
            user_name="同学",
            personality="耐心细致的教学老师",
            system_prompt="""你是陆墨老师，一位耐心细致的材料科学教师。

教学方法：
- 从基础概念讲起，循序渐进
- 使用类比和实例帮助理解
- 鼓励提问和思考
- 提供拓展阅读材料

特别擅长：
- 晶体结构与相变
- 材料制备原理
- 表征技术介绍
- 物理化学基础""",
            style_params={
                "formality": 0.6,
                "technical_depth": 0.7,
                "verbosity": 0.9,
                "proactivity": 0.9,
            },
            bio="材料科学教学模式",
            voice="zh-CN-XiaoxiaoNeural",
        )
        
        # 创意模式人设
        self._personas["creative"] = PersonaConfig(
            ai_name="陆墨",
            user_name="遥",
            personality="富有创造力的研究伙伴",
            system_prompt="""你是陆墨，一位富有创造力的研究伙伴。

思维特点：
- 善于跨学科联想
- 提出新颖的研究思路
- 鼓励探索非常规路径
- 关注技术前沿和交叉领域

讨论风格：
- 开放包容，乐于讨论各种想法
- 提供多角度分析
- 激发研究灵感""",
            style_params={
                "formality": 0.4,
                "technical_depth": 0.8,
                "verbosity": 0.7,
                "proactivity": 1.0,
            },
            bio="创意研究模式",
            voice="zh-CN-XiaoxiaoNeural",
        )
    
    def get_persona(self, name: str = None) -> PersonaConfig:
        """获取人设配置"""
        persona_name = name or self._active_persona
        if persona_name not in self._personas:
            logger.warning(f"人设 '{persona_name}' 不存在，使用默认")
            return self._personas["default"]
        return self._personas[persona_name]
    
    def set_active_persona(self, name: str) -> bool:
        """设置当前活跃人设"""
        if name not in self._personas:
            logger.error(f"人设 '{name}' 不存在")
            return False
        self._active_persona = name
        logger.info(f"切换人设: {name}")
        return True
    
    def get_active_persona_name(self) -> str:
        """获取当前活跃人设名称"""
        return self._active_persona
    
    def list_personas(self) -> list[dict[str, Any]]:
        """列出所有人设"""
        result = []
        for name, config in self._personas.items():
            result.append({
                "name": name,
                "ai_name": config.ai_name,
                "personality": config.personality,
                "bio": config.bio,
                "is_active": name == self._active_persona,
            })
        return result
    
    def create_persona(self, name: str, config: PersonaConfig) -> bool:
        """创建新人设"""
        if name in self._personas:
            logger.error(f"人设 '{name}' 已存在")
            return False
        self._personas[name] = config
        logger.info(f"创建人设: {name}")
        return True
    
    def update_persona(self, name: str, **kwargs) -> bool:
        """更新人设"""
        if name not in self._personas:
            logger.error(f"人设 '{name}' 不存在")
            return False
        
        config = self._personas[name]
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        logger.info(f"更新人设: {name}")
        return True
    
    def delete_persona(self, name: str) -> bool:
        """删除人设"""
        if name == "default":
            logger.error("不能删除默认人设")
            return False
        
        if name not in self._personas:
            logger.error(f"人设 '{name}' 不存在")
            return False
        
        del self._personas[name]
        
        # 如果删除的是当前活跃人设，切换到默认
        if name == self._active_persona:
            self._active_persona = "default"
        
        logger.info(f"删除人设: {name}")
        return True
    
    def get_system_prompt(self, name: str = None) -> str:
        """获取系统提示词"""
        persona = self.get_persona(name)
        return persona.system_prompt
    
    def get_style_params(self, name: str = None) -> dict[str, Any]:
        """获取风格参数"""
        persona = self.get_persona(name)
        return persona.style_params.copy()
    
    def set_style_param(self, key: str, value: float, name: str = None) -> bool:
        """设置单个风格参数"""
        persona = self.get_persona(name)
        if key not in persona.style_params:
            logger.warning(f"风格参数 '{key}' 不存在")
            return False
        persona.style_params[key] = max(0.0, min(1.0, value))
        return True
    
    def save_personas(self, file_path: str = None) -> bool:
        """保存人设到文件"""
        try:
            if file_path is None:
                from system.config import get_data_dir
                file_path = str(get_data_dir() / "personas.json")
            
            data = {
                "active_persona": self._active_persona,
                "personas": {}
            }
            
            for name, config in self._personas.items():
                data["personas"][name] = config.model_dump()
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"人设保存成功: {file_path}")
            return True
        except Exception as e:
            logger.error(f"人设保存失败: {e}")
            return False
    
    def load_personas(self, file_path: str = None) -> bool:
        """从文件加载人设"""
        try:
            if file_path is None:
                from system.config import get_data_dir
                file_path = str(get_data_dir() / "personas.json")
            
            if not Path(file_path).exists():
                return False
            
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            
            for name, config_data in data.get("personas", {}).items():
                self._personas[name] = PersonaConfig(**config_data)
            
            self._active_persona = data.get("active_persona", "default")
            logger.info(f"人设加载成功: {file_path}")
            return True
        except Exception as e:
            logger.error(f"人设加载失败: {e}")
            return False


def get_persona_manager() -> PersonaManager:
    """获取全局人设管理器（线程安全单例）"""
    global _persona_manager
    # HIGH-5: 双检锁模式
    if _persona_manager is None:
        with _persona_lock:
            if _persona_manager is None:
                _persona_manager = PersonaManager()
    return _persona_manager
