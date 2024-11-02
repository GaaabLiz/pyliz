from loguru import logger

from ai.core.ai_setting import AiSetting, AiQuery
from ai.runner.ai_runner import AiRunner
from util.pylizdir import PylizDir


class AiCommonRunner:

    @staticmethod
    def run_query(pyliz_dir: PylizDir, ai_setting: AiSetting, prompt: str, media_path: str | None = None) -> str:
        query = AiQuery(ai_setting, prompt, media_path)
        ai_result = AiRunner(pyliz_dir).run(query)
        if not ai_result.status:
            raise ValueError(ai_result.error)
        logger.info(f"RunForMedia (pixel) result.status = {ai_result.status}")
        logger.info(f"RunForMedia (pixel) result.payload = {ai_result.payload}")
        return ai_result.payload