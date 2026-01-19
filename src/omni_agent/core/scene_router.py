"""场景路由器，用于自动任务分类与路由。"""

import logging
from typing import Dict, List, Optional

from omni_agent.core.scene import SceneConfig, SceneType
from omni_agent.core.scene_registry import SCENE_CONFIGS

logger = logging.getLogger(__name__)


class SceneRouter:
    """自动场景检测与配置选择的路由器。

    支持两种匹配策略：
    1. 基于规则匹配（快速，使用关键词）
    2. LLM 分类（可选，更精确）
    """

    def __init__(
        self,
        llm_client: Optional["LLMClient"] = None,
        use_llm_classification: bool = False,
        custom_configs: Optional[Dict[SceneType, SceneConfig]] = None,
    ):
        """初始化场景路由器。

        Args:
            llm_client: 用于分类的 LLM 客户端（可选）
            use_llm_classification: 是否使用 LLM 进行分类
            custom_configs: 自定义场景配置，会与默认配置合并
        """
        self.llm_client = llm_client
        self.use_llm_classification = use_llm_classification

        self.configs = {**SCENE_CONFIGS}
        if custom_configs:
            self.configs.update(custom_configs)

    async def route(self, message: str) -> SceneConfig:
        """将消息路由到合适的场景配置。

        Args:
            message: 用户输入消息

        Returns:
            匹配场景的 SceneConfig
        """
        matched = self._rule_based_match(message)

        if matched and matched.priority >= 10:
            logger.info(
                f"通过规则路由场景: {matched.scene_type.value} (优先级={matched.priority})"
            )
            return matched

        if self.use_llm_classification and self.llm_client:
            llm_scene = await self._llm_classify(message)
            if llm_scene:
                config = self.configs.get(llm_scene, self.configs[SceneType.GENERAL])
                logger.info(f"通过 LLM 路由场景: {config.scene_type.value}")
                return config

        if matched:
            logger.info(
                f"通过规则路由场景（低优先级）: {matched.scene_type.value}"
            )
            return matched

        logger.info("路由到 GENERAL 场景（无匹配）")
        return self.configs[SceneType.GENERAL]

    def route_sync(self, message: str) -> SceneConfig:
        """同步路由方法（仅基于规则）。

        Args:
            message: 用户输入消息

        Returns:
            匹配场景的 SceneConfig
        """
        matched = self._rule_based_match(message)
        if matched:
            return matched
        return self.configs[SceneType.GENERAL]

    def _rule_based_match(self, message: str) -> Optional[SceneConfig]:
        """使用关键词规则匹配场景。

        Args:
            message: 用户输入消息

        Returns:
            最佳匹配的 SceneConfig 或 None
        """
        message_lower = message.lower()

        candidates: List[SceneConfig] = []

        for scene_type, config in self.configs.items():
            if scene_type == SceneType.GENERAL:
                continue

            for keyword in config.keywords:
                if keyword.lower() in message_lower:
                    candidates.append(config)
                    break

        if not candidates:
            return None

        candidates.sort(key=lambda c: c.priority, reverse=True)
        return candidates[0]

    async def _llm_classify(self, message: str) -> Optional[SceneType]:
        """使用 LLM 进行场景分类。

        Args:
            message: 用户输入消息

        Returns:
            分类的 SceneType 或 None（分类失败时）
        """
        if not self.llm_client:
            return None

        scene_descriptions = "\n".join(
            [
                f"- {st.value}: {self.configs[st].system_prompt_prefix or st.value}"
                for st in SceneType
            ]
        )

        prompt = f"""根据用户输入，判断最匹配的任务场景类型。

可选场景:
{scene_descriptions}

用户输入: {message}

只返回场景类型的值（如 code_development），不要其他内容。"""

        try:
            from omni_agent.schemas.message import Message

            response = await self.llm_client.generate(
                messages=[Message(role="user", content=prompt)],
                tools=None,
            )
            scene_value = response.content.strip().lower()
            return SceneType(scene_value)
        except (ValueError, Exception) as e:
            logger.warning(f"LLM 分类失败: {e}")
            return None

    def get_scene_by_name(self, name: str) -> Optional[SceneConfig]:
        """通过名称获取场景配置。

        Args:
            name: 场景类型名称（如 'code_development'）

        Returns:
            SceneConfig 或 None（未找到时）
        """
        try:
            scene_type = SceneType(name)
            return self.configs.get(scene_type)
        except ValueError:
            return None

    def list_scenes(self) -> List[str]:
        """列出所有可用的场景名称。

        Returns:
            场景类型名称列表
        """
        return [st.value for st in self.configs.keys()]
