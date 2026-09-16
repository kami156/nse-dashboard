SECTOR_INDICES = [
    ("NIFTY BANK", "^NSEBANK", "BANK"),
    ("NIFTY IT", "^CNXIT", "IT"),
    ("NIFTY PHARMA", "^CNXPHARMA", "PHARMA"),
    ("NIFTY AUTO", "^CNXAUTO", "AUTO"),
    ("NIFTY FMCG", "^CNXFMCG", "FMCG"),
    ("NIFTY METAL", "^CNXMETAL", "METAL"),
    ("NIFTY REALTY", "^CNXREALTY", "REALTY"),
    ("NIFTY INFRA", "^CNXINFRA", "INFRA"),
    ("NIFTY ENERGY", "^CNXENERGY", "ENERGY"),
    ("NIFTY FIN SERVICE", "^CNXFIN", "FIN"),
]

BENCHMARK = "^NSEI"

NSE_BENCHMARK_NAME = "NIFTY 50"

NSE_INDEX_NAMES = {
    "NIFTY BANK": "NIFTY BANK",
    "NIFTY IT": "NIFTY IT",
    "NIFTY PHARMA": "NIFTY PHARMA",
    "NIFTY AUTO": "NIFTY AUTO",
    "NIFTY FMCG": "NIFTY FMCG",
    "NIFTY METAL": "NIFTY METAL",
    "NIFTY REALTY": "NIFTY REALTY",
    "NIFTY INFRA": "NIFTY INFRASTRUCTURE",
    "NIFTY ENERGY": "NIFTY ENERGY",
    "NIFTY FIN SERVICE": "NIFTY FINANCIAL SERVICES",
}

NSE_SYMBOLS = {
    "TMCV": "TATAMOTORS",
    "SMLMAH": "SMLISUZU",
}

TIER_ORDER = ["large", "mid", "small", "micro"]
TIER_LABELS = {
    "large": "Large-Cap",
    "mid": "Mid-Cap",
    "small": "Small-Cap",
    "micro": "Micro-Cap",
}

UNIVERSE = {
    "BANK": {
        "large": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"],
        "mid": ["INDUSINDBK", "FEDERALBNK", "IDFCFIRSTB", "AUBANK", "BANDHANBNK"],
        "small": ["KARURVYSYA", "SOUTHBANK", "CSBBANK", "DCBBANK", "YESBANK"],
        "micro": ["CUB", "PSB"],
    },
    "IT": {
        "large": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM"],
        "mid": ["COFORGE", "LTTS", "PERSISTENT", "ZENSARTECH", "MPHASIS"],
        "small": ["TATAELXSI", "KPITTECH", "MASTEK", "CYIENT", "SONATSOFTW"],
        "micro": ["ROUTE", "RSYSTEMS"],
    },
    "PHARMA": {
        "large": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "ZYDUSLIFE"],
        "mid": ["AUROPHARMA", "LUPIN", "TORNTPHARM", "ALKEM", "IPCALAB"],
        "small": ["GLENMARK", "JUBLPHARMA", "GRANULES", "LAURUSLABS", "SYNGENE"],
        "micro": ["ORCHPHARMA", "HESTERBIO", "INDOCO"],
    },
    "AUTO": {
        "large": ["MARUTI", "TMCV", "M&M", "BAJAJ-AUTO", "EICHERMOT"],
        "mid": ["MOTHERSON", "BHARATFORG", "TVSMOTOR", "HEROMOTOCO", "EXIDEIND"],
        "small": ["ASHOKLEY", "ESCORTS", "APOLLOTYRE"],
        "micro": ["SMLMAH", "TALBROAUTO", "SHARDAMOTR"],
    },
    "FMCG": {
        "large": ["HINDUNILVR", "ITC", "NESTLEIND", "GODREJCP", "BRITANNIA"],
        "mid": ["MARICO", "DABUR", "COLPAL", "HATSUN", "VBL"],
        "small": ["GODREJAGRO", "BAJAJCON", "TATACONSUM"],
        "micro": ["ZYDUSWELL", "VSTIND"],
    },
    "METAL": {
        "large": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "SAIL"],
        "mid": ["HINDZINC", "JINDALSTEL", "APLAPOLLO", "RATNAMANI"],
        "small": ["NATIONALUM", "WELCORP", "HEG", "GRAPHITE"],
        "micro": ["JTLIND", "SURYAROSNI"],
    },
    "REALTY": {
        "large": ["DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "LODHA"],
        "mid": ["BRIGADE", "PHOENIXLTD", "SOBHA", "MAHLIFE"],
        "small": ["ANANTRAJ", "SUNTECK"],
        "micro": ["ASHIANA"],
    },
    "INFRA": {
        "large": ["LT", "ADANIPORTS", "SIEMENS"],
        "mid": ["GMRAIRPORT", "IRB", "IRCON"],
        "small": ["NCC", "KEC", "RVNL", "PNCINFRA"],
        "micro": ["TITAGARH", "HCC"],
    },
    "ENERGY": {
        "large": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "BPCL"],
        "mid": ["HINDPETRO", "IOC", "GAIL", "ADANIGREEN", "TATAPOWER"],
        "small": ["JSWENERGY", "NHPC", "SJVN", "ADANIENSOL"],
        "micro": ["RPOWER", "NLCINDIA"],
    },
    "FIN": {
        "large": ["BAJFINANCE", "BAJAJFINSV", "SBILIFE", "ICICIPRULI"],
        "mid": ["SBICARD", "HDFCAMC", "LICHSGFIN", "CHOLAFIN"],
        "small": ["MUTHOOTFIN", "M&MFIN", "IIFL"],
        "micro": ["MASFIN", "VLSFINANCE"],
    },
}
