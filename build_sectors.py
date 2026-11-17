import json, csv, os
from collections import Counter

with open('mcap_cache.json', 'r', encoding='utf-8') as f:
    cache = json.load(f).get('stocks', {})

# Comprehensive Indian Market Sectors tailored for NSE equity screening
SECTORS = {
    "Banking & Financials": [
        "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BANKBARODA", "PNB", 
        "CANBK", "UNIONBANK", "MAHABANK", "INDIANB", "IOB", "UCOBANK", "CENTRALBK", 
        "PSB", "IDFCFIRSTB", "FEDERALBNK", "RBLBANK", "AUBANK", "BANDHANBNK", "KARURVYSYA", 
        "KTKBANK", "CSBBANK", "YESBANK", "DHANBANK", "ESAFSFB", "BAJFINANCE", "BAJAJFINSV", 
        "CHOLAFIN", "SHRIRAMFIN", "MUTHOOTFIN", "MANAPPURAM", "LICHSGFIN", "PNBHOUSING", 
        "POONAWALLA", "SGFIN", "BFINVEST", "ARIHANTCAP", "ARSSBL", "360ONE", "MOTILALOFS", 
        "NUVAMA", "ANGELONE", "GROWW", "CAMS", "KFINTECH", "CDSL", "HDFCAMC", "UTIAMC", 
        "NAM-INDIA", "SBILIFE", "HDFCLIFE", "ICICIPRULI", "ICICIGI", "LICI", "GICRE", 
        "NIACL", "BAJAJHLDNG", "PAYTM", "GEOJITFSL", "J&KBANK", "SOUTHBANK", "FINOPB", 
        "M&MFIN", "SUNDARMFIN", "CREDITACC", "FIVESTAR", "AAVAS", "HOMEFIRST", "CANFINHOME", 
        "HUDCO", "PFC", "RECLTD", "IREDA", "IFCI", "SBIFUNDS", "ALGOQUANT", "BAJAJHFL",
        "NORTHARC", "MUFIN", "TMB", "TFCILTD", "ANANDRATHI", "SHAREINDIA", "PRUDENT",
        "EDELWEISS", "JM FINANCIAL", "IIFL", "ISEC", "MONARCH", "RELIGARE", "SMCGLOBAL"
    ],
    "Automobiles & Auto Parts": [
        "MARUTI", "M&M", "TATAMOTORS", "TMCV", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO", 
        "TVSMOTOR", "ASHOKLEY", "ESCORTS", "FORCE", "FORCEMOT", "OLECTRA", "JBMMA", 
        "MOTHERSON", "BOSCHLTD", "BALKRISIND", "MRF", "APOLLOTYRE", "CEAT", "JKTYRE", 
        "EXIDEIND", "AMARAJABAT", "LUMAXTECH", "SANDHAR", "TALBROAUTO", "SHARDAMOTR", 
        "UNOMINDA", "CRAFTSMAN", "RACLGEAR", "GULFOILLUB", "SUBROS", "SUNDRMFAST", 
        "ENDURANCE", "VARROC", "TIMKEN", "SCHAEFFLER", "SKFINDIA", "SUPRAJIT", "PRICOLLTD", 
        "GABRIEL", "JAMNAAUTO", "ROLEXRINGS", "SANSERA", "CIEINDIA", "HYUNDAI", "ALICON",
        "TVSSRICHAK", "MSUMI", "GREAVESCOT", "TIINDIA", "MAHSCOOTER", "FIEMIND", "BANCOINDIA",
        "MUNJALAU", "LUMAXIND", "JAYBARMARU", "SHRIRAMPPS", "AUTOAXLES", "MAHINDCIE"
    ],
    "IT & Software Services": [
        "TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM", "COFORGE", "PERSISTENT", 
        "MPHASIS", "KPITTECH", "TATAELXSI", "OFSS", "CYIENT", "CYIENTDLM", "ZOMATO", 
        "SWIGGY", "POLICYBZR", "63MOONS", "SASKEN", "BLSE", 
        "MAPMYINDIA", "RATEGAIN", "TANLA", "ROUTE", "NEWGEN", "MASTEK", "BSOFT", 
        "LATENTVIEW", "HAPPSTMNDS", "SONATSOFTW", "ZENSARTECH", "INTELLECT", "NETWEB", 
        "ECLERX", "FSL", "REDINGTON", "AFFLE", "NAZARA", "ONMOBILE", "KODYTECH",
        "ONEPOINT", "ROSSTECH", "PANACHE", "DATAPATTNS", "CELEBRITY", "MOSCHIP", "NELCO",
        "SAKSOFT", "SUBEXLTD", "AURIONPRO", "GENESYS", "QUESS", "TEAMLEASE"
    ],
    "Pharma & Healthcare": [
        "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "LUPIN", "AUROPHARMA", "TORNTPHARM", 
        "ALKEM", "ZYDUSLIFE", "MANKIND", "BIOCON", "GLENMARK", "IPCALAB", "LAURUSLABS", 
        "ABBOTINDIA", "PFIZER", "SANOFI", "GLAXO", "APOLLOHOSP", "FORTIS", "MAXHEALTH", 
        "MEDANTA", "YATHARTH", "ARTEMISMED", "KOVAI", "VIJAYA", "LALPATHLAB", "METROPOLIS", 
        "KIMS", "RAINBOW", "ASTERDM", "SUDEEPPHRM", "NEULANDLAB", "AARTIPHARM", "APLLTD", 
        "ALEMBICLTD", "PPLPHARMA", "ERIS", "NATCOPHARM", "GRANULES", "JBCHEPHARM", "FDC", 
        "AJANTPHARM", "GLAND", "CAPLIPOI", "MARKSANS", "HIKAL", "CONCORDBIO", "INNOVACAP", 
        "BLUEJET", "RUBICON", "KMCSHIL", "FREDUN", "KPL", "MANIPALHOS", "NEPHROPLUS",
        "SURAKSHA", "THYROCARE", "SHILPAMED", "WOCKPHARMA", "SMSPHARMA", "STRIDES", "HIL",
        "SEQUENT", "SOLARA", "SUVEN", "AARTIDRUGS", "SUPRIYA", "SIGACHI"
    ],
    "Defense & Aerospace": [
        "HAL", "BEL", "BDL", "MAZDOCK", "COCHINSHIP", "GRSE", "SWANDEF", "ASTRAMICRO",
        "MTARTECH", "PARAS", "ZENTEC", "DCXINDIA", "APOLLO", "DATAPATTNS", "DYNAMATECH",
        "MIDHANI", "BHARATFORG", "PREMEXPLN"
    ],
    "Energy, Power & Utilities": [
        "RELIANCE", "ONGC", "IOC", "BPCL", "HPCL", "GAIL", "NTPC", "POWERGRID", "TATAPOWER", 
        "ADANIGREEN", "ADANIPOWER", "ADANIENSOL", "TORNTPOWER", "KPIGREEN", "HINDOILEXP", 
        "PETRONET", "OIL", "NHPC", "SJVN", "JSWENERGY", "CESC", "IEX", "SUZLON", 
        "INOXWIND", "PREMIERENE", "WAAREE", "GIPCL", "JPPOWER", "RPOWER", "GUJGASLTD", 
        "IGL", "MGL", "DEEPINDS", "STEAMHOUSE", "PACEDIGITK", "RPEL", "GENUSPOWER",
        "ENERGYDEV", "NLCINDIA", "ORIENTGREEN", "INDOSTAR", "ENIL"
    ],
    "Real Estate & Infrastructure": [
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "PHOENIXLTD", "BRIGADE", "SOBHA", 
        "SIGNATURE", "SUNTECK", "AJMERA", "LOTUSDEV", "AGIIL", "MACROTECH", "KOLTEPATIL", 
        "MAHLIFE", "PURVA", "LT", "NCC", "PNCINFRA", "KNRCON", "IRB", "CEMPRO", 
        "GRINFRA", "HGINFRA", "ASHOKA", "AHLUCONT", "ITD", "MANINFRA", "NBCC", "GMRINFRA", 
        "ULTRACEMCO", "AMBUJACEM", "ACC", "SHREECEM", "DALBHARAT", "NUVOCO", "RAMCOCEM", 
        "JKCEMENT", "HEIDELBERG", "BIRLACORPN", "MINDSPACE.RR", "CAPINVIT", "NIRLON",
        "ARIS", "WEWORK", "ENGINERSIN", "CEMINDIA", "JPASSOCIAT", "HCC", "RITES", "IRCON",
        "RVNL", "RAILTEL", "BOMDYEING", "PENINLAND", "DBREALTY", "GLASSWALL", "IGIL"
    ],
    "Capital Goods & Engineering": [
        "BHEL", "ABB", "SIEMENS", "CUMMINSIND", "THERMAX", "KDDL", "QPOWER", "JASH", 
        "KMEW", "ISGEC", "CENTUM", "AJAXENGG", "POLYCAB", "KEI", "RRKABEL", "HAVELLS", 
        "AIAENG", "CARBORUN", "GRINDWELL", "ELGIEQUIP", "TRITURBINE", "KIRLOSENG", 
        "TDPOWERSYS", "TCPLPACK", "KABRAEXTRU", "SPECTRUM", "KSHINTL", "MARSONS", 
        "KERNEX", "ELECON", "PRAJIND", "GMM PFAUDLER", "ESABINDIA", "DISA", "WALCHANNAG", 
        "KIRLOSBROS", "TEXRAIL", "TITAGARH", "JUPITERWAG", "BEML", "KEC", "SGMART"
    ],
    "Metals, Mining & Steel": [
        "TATASTEEL", "JSWSTEEL", "JINDALSTEL", "SAIL", "HINDALCO", "VEDL", "NATIONALUM", 
        "NMDC", "COALINDIA", "VAML", "SHYAMMETL", "VSSL", "GOODLUCK", "STEELCAS", 
        "APLAPOLLO", "JINDALSAW", "RATNAMANI", "WELCORP", "SURYA", "KIRLFER", "USHAMART", 
        "GRAVITA", "MOIL", "KIOCL", "HINDZINC", "SALSTEEL", "MONOLITH", "CMLL", "NRL",
        "GPIL", "JAYASWAL", "MAITHANALL", "GALLANTT", "ELECTCAST", "TATASTEELBSL"
    ],
    "Chemicals & Fertilizers": [
        "PIDILITIND", "DEEPAKNTR", "SRF", "NAVINFLUOR", "FLUOROCHEM", "AARTIIND", "ATUL", 
        "TATACHEM", "DEEPAKFERT", "COROMANDEL", "CHEMPLASTS", "ANURAS", "AETHER", 
        "NEOGEN", "GHCL", "UPL", "PIIND", "DHANUKA", "SUMICHEM", "RALLIS", "SHARDACROP", 
        "BHARATRAS", "FINEORG", "CLEAN", "AMIORG", "ROSSARI", "EPIGRAL", "SUDARSCHEM", 
        "CHAMBLFERT", "GNFC", "GSFC", "FACT", "RCF", "XPROINDIA", "ASIANPAINT", "BERGEPAINT",
        "KANSAINER", "INDIGOPNTS", "TFL", "VALIANTORG", "FINEOTEX", "CHEMCON", "YASHCHEM"
    ],
    "Consumer Durables & Electronics": [
        "VOLTAS", "BLUESTARCO", "AMBER", "DIXON", "KAYNES", "SYRMA", "PGEL", "CROMPTON",
        "ORIENTELEC", "SYMPHONY", "WHIRLPOOL", "BAJAJELEC", "VGUARD", "IFBIND", "TTKPRESTIG",
        "HAWKINS", "EUREKAFORB", "BOROLTD", "ASAHIINDIA", "STOVEKRAFT", "BUTTERFLY",
        "NILKAMAL", "ETERNAL"
    ],
    "FMCG, Food & Beverages": [
        "HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "MARICO", "COLPAL", 
        "GODREJCP", "EMAMILTD", "TATACONSUM", "VBL", "RADICO", "ABDL", "BECTORFOOD", 
        "HONASA", "WESTLIFE", "RBA", "JUBLFOOD", "DEVYANI", "SAPPHIRE", "PATANJALI", 
        "BIKAJI", "GOPAL", "PRATAAP", "KRBL", "LTFOODS", "PARAGMILK", "HERITGFOOD", 
        "DODLA", "HATSUN", "TASTYBITE", "AVTNPL", "SULA", "TI", "UNITEDSPR", "GMBLIE"
    ],
    "Retail, Fashion & Textiles": [
        "TRENT", "DMART", "STYLEBAAZA", "PAGEIND", "KPRMILL", "WELSPUNLIV", "RAYMOND", 
        "GOKEX", "FILATEX", "SPORTKING", "PGIL", "SANGAMIND", "NITINSPIN", "GHCLTEXTIL", 
        "AYMSYNTEX", "TRIDENT", "ALOKINDS", "GARFIBRES", "LUXIND", "RUPA", "DOLLAR", 
        "FAZE3Q", "UNITEDPOLY", "ICIL", "VMART", "LENSKART", "FIRSTCRY", "RELAXO", 
        "BATAINDIA", "CAMPUS", "METRO", "TITAN", "KALYANKJIL", "SENCO", "THANGAMAYL", 
        "MANYAVAR", "SHOPERSTOP", "ABFRL", "VEDANTFASH", "ARVIND", "CENTURYTEX", "SWAN",
        "MEESHO"
    ],
    "Hotels, Tourism & Leisure": [
        "INDHOTEL", "EIHOTEL", "CHALET", "LEMONTREE", "ORIENTHOT", "THELEELA", "ITCHOTELS",
        "DELTACORP", "THOMASCOOK", "IXIGO", "EASEMYTRIP", "BLS", "YATRA", "SPECIALITY",
        "PARK", "SAMHI", "MAHINDCIE", "WONDERLA", "DELTA"
    ],
    "Telecom, Media & Entertainment": [
        "BHARTIARTL", "BHARTIHEXA", "TATACOMM", "INDUSTOWER", "SUNTV", "ZEEL", 
        "SAREGAMA", "TIPSMUSIC", "PVRINOX", "NETWORK18", "TV18BRDCST", "DEN", "HATHWAY",
        "DISHTV", "GTPL", "RADIO CITY", "JAGRAN", "DBCORP"
    ],
    "Logistics, Shipping & Aviation": [
        "ADANIPORTS", "CONCOR", "DELHIVERY", "GESHIP", "SCI", "SHREEJISPG", "VRLLOG", 
        "TVSSCS", "INDIGO", "GMRAIRPORT", "LEAPIND", "ALLCARGO", "MAHLOG", "TCI", 
        "BLUEDART", "DOLPHIN", "SHADOWFAX", "SPIC", "SEAMECLTD", "GATEWAY", "CONTAINER"
    ],
    "Paper, Packaging & Containers": [
        "UFLEX", "COMSYN", "JKPAPER", "WESTCOASTP", "TNPL", "ANDHRAPAP", "SESHAPAPER",
        "ASTRAL", "SUPREMEIND", "FINOLEXIND", "PRINCEPIPE", "POLYPLEX", "TIMETECHNO",
        "EPL", "HUHTAMAKI", "TCPLPACK", "MOLDTKPAK"
    ]
}

# Create inverted dictionary
symbol_to_sector = {}
for sector, syms in SECTORS.items():
    for s in syms:
        symbol_to_sector[s] = sector

def get_heuristic_sector(sym):
    u = sym.upper()
    if any(k in u for k in ["BANK", "FIN", "CAP", "INVEST", "HOLD", "HLDNG", "AMC", "INSUR", "HSG", "SECUR"]):
        return "Banking & Financials"
    if any(k in u for k in ["DEFENCE", "DEFENSE", "AERO", "DYNAM"]):
        return "Defense & Aerospace"
    if any(k in u for k in ["AUTO", "MOTOR", "TYRE", "GEAR", "WHEEL", "CAST", "FORG"]):
        return "Automobiles & Auto Parts"
    if any(k in u for k in ["TECH", "SOFT", "INFO", "DIGI", "CYBER", "NETW"]):
        return "IT & Software Services"
    if any(k in u for k in ["PHARM", "HEALTH", "MED", "BIO", "LAB", "HOSP", "CLINIC"]):
        return "Pharma & Healthcare"
    if any(k in u for k in ["POWER", "ENERGY", "SOLAR", "WIND", "OIL", "GAS", "PETRO"]):
        return "Energy, Power & Utilities"
    if any(k in u for k in ["HOTEL", "RESORT", "TRAVEL", "HOLIDAY"]):
        return "Hotels, Tourism & Leisure"
    if any(k in u for k in ["REALTY", "PROP", "INFRA", "CONST", "ESTATE", "DEV", "BUILD", "CEMENT"]):
        return "Real Estate & Infrastructure"
    if any(k in u for k in ["STEEL", "MET", "MINE", "IRON", "ALLOY", "ZINC", "ALUM", "PIPE", "TUBE"]):
        return "Metals, Mining & Steel"
    if any(k in u for k in ["CHEM", "FERT", "AGRO", "PEST", "ORGAN"]):
        return "Chemicals & Fertilizers"
    if any(k in u for k in ["TEXTIL", "SPIN", "WEAV", "YARN", "FABRIC", "COTTON", "SILK", "MILL", "GARMENT", "APPAREL", "FASHION"]):
        return "Retail, Fashion & Textiles"
    if any(k in u for k in ["FOOD", "RETAIL", "BEV", "BREW", "DAIRY", "SUGAR", "CONSUM", "SWEET", "TEA", "COFFEE"]):
        return "FMCG, Food & Beverages"
    if any(k in u for k in ["ELEC", "APPLIANCE", "DURABLE"]):
        return "Consumer Durables & Electronics"
    if any(k in u for k in ["LOGIST", "PORT", "SHIP", "TRANS", "AIR"]):
        return "Logistics, Shipping & Aviation"
    if any(k in u for k in ["PAPER", "PACK"]):
        return "Paper, Packaging & Containers"
    if any(k in u for k in ["MEDIA", "TELE", "CABLE", "FILM", "COMM", "ENTERTAIN", "NEWS", "PRINT"]):
        return "Telecom, Media & Entertainment"
    if any(k in u for k in ["ENGG", "MACHIN", "TOOLS", "POWER", "IND", "EQUIP"]):
        return "Capital Goods & Engineering"
    return "Diversified & Conglomerates"

all_sectors = {}
for s in cache:
    if s in symbol_to_sector:
        all_sectors[s] = symbol_to_sector[s]
    else:
        all_sectors[s] = get_heuristic_sector(s)

with open('sectors.json', 'w', encoding='utf-8') as f:
    json.dump(all_sectors, f, indent=2)

print(f"Generated sectors.json for {len(all_sectors)} stocks.")

counts = Counter([all_sectors[s] for s in all_sectors])
for sec, cnt in counts.most_common():
    print(f"  • {sec:32}: {cnt}")
