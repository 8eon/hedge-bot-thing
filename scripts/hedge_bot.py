"""
Hedge-bot Hummingbot V2 script entry point.

Start this script with:
    create --v2-config hedge_bot.py
    start --v2 conf/scripts/conf_hedge_bot_1.yml

This file is intentionally thin. All strategy logic lives in the controller.
The script's only job is to wire up the controller and expose the config to
Hummingbot's startup system.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controllers.avellaneda_stoikov_controller import (
    AvellanedaStoikovConfig,
    AvellanedaStoikovController,
)

from hummingbot.strategy_v2.strategy_v2_base import StrategyV2Base, StrategyV2ConfigBase
from pydantic import Field


class HedgeBotConfig(StrategyV2ConfigBase):
    """
    Top-level script configuration. Embeds the controller config so that a
    single YAML file configures the whole system.
    """
    script_file_name: str = Path(__file__).name
    controller_config: str = Field(
        default="controllers/conf_avellaneda_stoikov_1.yml",
        client_data=None,
    )


class HedgeBot(StrategyV2Base):
    """
    Minimal StrategyV2Base subclass that delegates all logic to
    AvellanedaStoikovController.
    """

    @classmethod
    def get_script_name(cls) -> str:
        return "hedge_bot"

    @classmethod
    def init_markets(cls, config: HedgeBotConfig) -> None:
        # Markets are configured inside the controller config.
        pass
