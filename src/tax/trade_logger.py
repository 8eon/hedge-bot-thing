"""
Trade execution logger.

Every fill the bot receives is recorded here as a TradeRecord. The logger
appends records to a newline-delimited JSON file, which is the input for
cost basis accounting and IRS form generation downstream.

Design notes:
- Each record is self-contained: reading a single line gives you everything
  needed to reconstruct cost basis without cross-referencing other records.
- The file is append-only. Nothing is ever deleted or modified. This makes
  the log auditable and safe to read concurrently.
- Timestamps are always UTC ISO-8601. No local time, no ambiguity.
"""

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class TradeRecord:
    """
    A single executed trade, capturing every field required for IRS Form 8949.

    Attributes:
        trade_id:     Unique identifier assigned by the exchange.
        timestamp:    Execution time in UTC ISO-8601 format.
        exchange:     Exchange identifier (e.g. "binance", "binance_paper_trade").
        trading_pair: Market symbol (e.g. "BTC-USDT").
        side:         Whether this was a buy or a sell.
        base_asset:   The asset being bought or sold (e.g. "BTC").
        quote_asset:  The asset used as denomination (e.g. "USDT").
        quantity:     Amount of base asset transacted.
        price:        Execution price in quote asset per unit of base asset.
        fee:          Fee paid in fee_asset units.
        fee_asset:    Asset the fee was denominated in (commonly "BNB" or quote asset).
        order_id:     Exchange order ID this fill belongs to.
        is_paper:     True if this was a paper trading fill, not a real transaction.
                      Paper trades are excluded from tax calculations.
    """
    trade_id: str
    timestamp: str  # UTC ISO-8601
    exchange: str
    trading_pair: str
    side: TradeSide
    base_asset: str
    quote_asset: str
    quantity: float
    price: float
    fee: float
    fee_asset: str
    order_id: str
    is_paper: bool = False

    @property
    def gross_value(self) -> float:
        """Total value of the trade in quote asset, before fees."""
        return self.quantity * self.price

    @property
    def fee_in_quote(self) -> float:
        """
        Fee expressed in quote asset. If the fee was paid in the quote asset
        this is exact; otherwise it is an approximation that must be reconciled
        at cost-basis time using the fee asset's price at the trade timestamp.
        """
        if self.fee_asset == self.quote_asset:
            return self.fee
        # Caller must resolve cross-asset fees; return sentinel to flag this.
        return float("nan")

    @classmethod
    def now_utc(cls) -> str:
        return datetime.now(timezone.utc).isoformat()


class TradeLogger:
    """
    Thread-safe, append-only trade log backed by a newline-delimited JSON file.

    Usage:
        logger = TradeLogger(Path("logs/trades.jsonl"))
        logger.record(trade)

    The log file is created (including parent directories) on first write.
    """

    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._lock = threading.Lock()

    def record(self, trade: TradeRecord) -> None:
        """Append a single trade to the log. Thread-safe."""
        line = json.dumps(asdict(trade), default=str) + "\n"
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)

    def read_all(self) -> list[TradeRecord]:
        """
        Load and deserialize every record from the log file.
        Returns an empty list if the file does not exist.
        """
        if not self._path.exists():
            return []

        records: list[TradeRecord] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                data["side"] = TradeSide(data["side"])
                records.append(TradeRecord(**data))
        return records

    def read_taxable(self) -> list[TradeRecord]:
        """Return only real (non-paper) trades for tax processing."""
        return [r for r in self.read_all() if not r.is_paper]
