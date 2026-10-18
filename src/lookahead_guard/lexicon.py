"""Word lists used by the rules: asset identifiers, dated market events, cues.

Everything here is a heuristic seed list meant to be extended. Users add
their own identifiers through ``entities``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Pattern

# --- Asset identifiers -------------------------------------------------------
# Ticker -> company names that identify the same asset. Tickers that are also
# common English words or trading jargon (A, T, F, C, V, MA, ALL, NOW, KEY,
# ON, IT, ...) are left out on purpose; cashtags ($T) still catch them.
ASSETS: Dict[str, List[str]] = {
    "AAPL": ["Apple"],
    "MSFT": ["Microsoft"],
    "NVDA": ["NVIDIA", "Nvidia"],
    "AMZN": ["Amazon"],
    "GOOGL": ["Alphabet", "Google"],
    "GOOG": ["Alphabet", "Google"],
    "META": ["Meta Platforms", "Facebook"],
    "TSLA": ["Tesla"],
    "BRK.B": ["Berkshire Hathaway"],
    "AVGO": ["Broadcom"],
    "JPM": ["JPMorgan", "JP Morgan"],
    "LLY": ["Eli Lilly"],
    "UNH": ["UnitedHealth"],
    "XOM": ["Exxon", "ExxonMobil"],
    "JNJ": ["Johnson & Johnson"],
    "WMT": ["Walmart"],
    "PG": ["Procter & Gamble"],
    "HD": ["Home Depot"],
    "COST": ["Costco"],
    "ORCL": ["Oracle"],
    "ABBV": ["AbbVie"],
    "MRK": ["Merck"],
    "CVX": ["Chevron"],
    "KO": ["Coca-Cola"],
    "PEP": ["PepsiCo"],
    "BAC": ["Bank of America"],
    "NFLX": ["Netflix"],
    "ADBE": ["Adobe"],
    "CRM": ["Salesforce"],
    "AMD": ["Advanced Micro Devices"],
    "INTC": ["Intel"],
    "CSCO": ["Cisco"],
    "MCD": ["McDonald's"],
    "DIS": ["Disney"],
    "WFC": ["Wells Fargo"],
    "QCOM": ["Qualcomm"],
    "IBM": [],
    "GS": ["Goldman Sachs"],
    "MS": ["Morgan Stanley"],
    "PFE": ["Pfizer"],
    "NKE": ["Nike"],
    "BA": ["Boeing"],
    "SBUX": ["Starbucks"],
    "PYPL": ["PayPal"],
    "UBER": ["Uber"],
    "SHOP": ["Shopify"],
    "PLTR": ["Palantir"],
    "COIN": ["Coinbase"],
    "SNOW": ["Snowflake"],
    "TSM": ["TSMC", "Taiwan Semiconductor"],
    "ASML": [],
    "SMCI": ["Super Micro Computer", "Supermicro"],
    "MU": ["Micron"],
    "ARM": ["Arm Holdings"],
    "GME": ["GameStop"],
    "SPY": ["SPDR S&P 500"],
    "QQQ": ["Invesco QQQ"],
    "IWM": [],
    "BTC": ["Bitcoin"],
    "ETH": ["Ethereum"],
}

# Ambiguous ticker spellings: skip the bare-uppercase match for these, keep
# the company-name match. "MS" (millisecond, multiple sclerosis), "BA",
# "PG", "HD", "KO", "MU", "GS", "ARM", "COST", "SHOP", "SNOW", "COIN" are
# common words or abbreviations in upper case headlines.
AMBIGUOUS_TICKERS = {"MS", "BA", "PG", "HD", "KO", "MU", "GS", "ARM", "COST", "SHOP", "SNOW", "COIN", "UBER", "DIS"}


@dataclass(frozen=True)
class Event:
    name: str
    first_known: date  # first day the event was public knowledge
    pattern: Pattern


def _ev(name: str, day: str, pattern: str) -> Event:
    y, m, d = (int(x) for x in day.split("-"))
    return Event(name, date(y, m, d), re.compile(pattern, re.IGNORECASE))


# Named market events. A prompt dated before ``first_known`` that names the
# event is anachronistic; one dated after it reveals the era to the model.
EVENTS: List[Event] = [
    _ev("Lehman Brothers bankruptcy", "2008-09-15", r"\bLehman(?: Brothers)? (?:bankruptcy|collapse|failure)\b"),
    _ev("Flash Crash", "2010-05-06", r"\b(?:2010 )?Flash Crash\b"),
    _ev("Taper tantrum", "2013-05-22", r"\btaper tantrum\b"),
    _ev("Brexit referendum result", "2016-06-24", r"\bBrexit (?:vote|referendum|result)\b"),
    _ev("Volmageddon", "2018-02-05", r"\bVolmageddon\b"),
    _ev("COVID-19", "2020-01-09", r"\b(?:COVID(?:-19)?|SARS-CoV-2|novel coronavirus)\b"),
    _ev("GameStop short squeeze", "2021-01-22", r"\bGameStop (?:short )?squeeze\b|\bmeme[- ]stock (?:mania|frenzy|rally)\b"),
    _ev("Archegos collapse", "2021-03-26", r"\bArchegos\b"),
    _ev("Evergrande default", "2021-12-09", r"\bEvergrande (?:default|collapse|crisis)\b"),
    _ev("Russia's invasion of Ukraine", "2022-02-24", r"\b(?:Russian? )?invasion of Ukraine\b|\bRussia invades Ukraine\b"),
    _ev("FTX collapse", "2022-11-08", r"\bFTX (?:collapse|bankruptcy|implosion|scandal)\b"),
    _ev("ChatGPT launch", "2022-11-30", r"\bChatGPT\b"),
    _ev("Silicon Valley Bank failure", "2023-03-10", r"\b(?:SVB|Silicon Valley Bank) (?:collapse|failure|crisis|run)\b"),
    _ev("Credit Suisse rescue", "2023-03-19", r"\bCredit Suisse (?:collapse|rescue|takeover)\b|\bUBS takeover of Credit Suisse\b"),
    _ev("First Republic failure", "2023-05-01", r"\bFirst Republic(?: Bank)? (?:collapse|failure|seizure)\b"),
    _ev("CrowdStrike outage", "2024-07-19", r"\bCrowdStrike (?:outage|incident|meltdown)\b"),
    _ev("Yen carry-trade unwind", "2024-08-05", r"\b(?:yen )?carry[- ]trade unwind\b"),
    _ev("DeepSeek-R1 release", "2025-01-20", r"\bDeepSeek[- ]R1\b"),
    _ev("'Liberation Day' tariffs", "2025-04-02", r"\bLiberation Day\b"),
]

# --- Cues around a date mention ---------------------------------------------
FORWARD_STRONG = re.compile(
    r"\b(?:will|shall|expected|expects?|scheduled|upcoming|due|forecast(?:s|ed)?|guidance|"
    r"estimates?|consensus|planned|plans? to|projected|anticipated|outlook|deadline|"
    r"expir(?:es|y|ation)|matur(?:es|ity)|if|could|may|might|potential(?:ly)?)\b",
    re.IGNORECASE,
)
FORWARD_WEAK = re.compile(r"\b(?:ahead of|into|before|by|until|next|through|pending)\b", re.IGNORECASE)
REALIZED = re.compile(
    r"\b(?:closed|opened|rose|fell|jumped|surged|soared|plunged|plummeted|dropped|tumbled|"
    r"rallied|gained|lost|declined|climbed|crashed|spiked|sank|slid|reported|announced|"
    r"beat|missed|ended|finished|hit|reached|peaked|bottomed|traded|settled|was|were|"
    r"became|turned out|went|delivered|posted|printed|cut|raised|hiked|filed|collapsed)\b",
    re.IGNORECASE,
)

HINDSIGHT = re.compile(
    r"\b(?:in hindsight|in retrospect|turned out|as we now know|looking back|"
    r"went on to|would (?:later|go on to|eventually|ultimately|soon)|subsequently|"
    r"later that (?:day|week|month|quarter|year)|the following (?:day|week|month|quarter|year)|"
    r"(?:ultimately|eventually) (?:rose|fell|rallied|crashed|recovered|collapsed|doubled|halved)|"
    r"never recovered|all-time high (?:later|that year))\b",
    re.IGNORECASE,
)
