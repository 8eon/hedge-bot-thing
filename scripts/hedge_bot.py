"""
Hedge-bot Hummingbot V2 script entry point.

Start this script with:
    start --script hedge_bot.py --conf conf_hedge_bot_1.yml

This file is intentionally thin. All strategy logic lives in the controller.
The script's only job is to declare which controller config(s) to load and
let StrategyV2Base wire everything up automatically via controllers_config.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hummingbot.strategy.strategy_v2_base import StrategyV2Base, StrategyV2ConfigBase
from pydantic import Field


class HedgeBotConfig(StrategyV2ConfigBase):
    """
    Top-level script configuration.

    controllers_config: list of filenames under conf/controllers/ to load.
    Each file configures one controller instance. The strategy base reads
    controller_type and controller_name from each YAML, imports the module
    at controllers.{controller_type}.{controller_name}, and instantiates the
    config class and controller automatically.
    """
    script_file_name: str = os.path.basename(__file__)
    controllers_config: List[str] = Field(
        default=["conf_avellaneda_stoikov_1.yml"],
        json_schema_extra={
            "prompt": "Controller config files (comma-separated, relative to conf/controllers/): ",
            "prompt_on_new": True,
        },
    )


class HedgeBot(StrategyV2Base):
    """
    Minimal StrategyV2Base subclass that delegates all logic to the controller(s)
    listed in HedgeBotConfig.controllers_config.

    init_markets is handled by the base class: it calls load_controller_configs(),
    iterates each controller config's update_markets(), and registers the resulting
    connector/pair set with the exchange connector factory.
    """
    pass
