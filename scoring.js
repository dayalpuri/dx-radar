/*
 * scoring.js — JEDINÝ ZDROJ laditelných konstant skóre pro DX Radar.
 *
 * Čtou ho OBA kódy:
 *   - index.html (PWA): načte přes <script src="scoring.js"> jako window.SCORING,
 *   - eibi_sync.py (CLI): vytáhne níže uvedený JSON blok a json.loads ho.
 *
 * Objekt uvnitř MUSÍ zůstat čistý JSON (bez komentářů, bez koncových čárek,
 * bez JS výrazů), aby ho Python spolehlivě rozparsoval. Laď jen tady — změna
 * se propíše do aplikace i do CLI radaru, takže se obě strany nerozejdou.
 *
 * iono: propagační a skip člen počítané po skocích přes vrstvu F2 (výška layerKm,
 * skok nejvýš maxHopKm, paprsek nejníž minElevDeg nad obzorem). V bodě odrazu každého
 * skoku se odhadne kritický kmitočet foF2:
 *   den   = dayBase + dayFlux·s, kde s = (SFI − 60)/140 (0 až 1,5),
 *   noční minimum = nightBase + nightFlux·s ± sezóna (seasonSummer / seasonWinter krát
 *     deklinace/23,44° pro danou polokouli; letní noc vrstva nestihne zaniknout, proto
 *     je letní přídavek větší než zimní úbytek), nejméně nightFloor,
 *   večer = minimum + eveFrac·(den − minimum), klesá lineárně decayH hodin od 18 h
 *     místního slunečního času,
 *   přechod den/noc plynule podle výšky Slunce mezi smoothFromDeg (−18° = Slunce už
 *     nesvítí ani do výšky vrstvy) a smoothToDeg, vyhodnocené o lagH hodin dřív.
 *   polarMul / equatorDayBoost = hrubá oprava pro šířky nad 60° a pod 25°; při Kp nad
 *     stormKp klesá foF2 o stormDrop na stupeň Kp.
 * MUF trasy = nejnižší foF2 ze všech skoků × šikmý faktor M skoku. Šance, že kmitočet
 * projde, je logistická křivka kolem MUF se šířkou mufSigma·MUF; neprojde-li, stojí to
 * až mufPenalty bodů. Ta se dělí na dva členy: co neprojde ani nejdelším skokem, je
 * zavřené pásmo (propagační člen); co by prošlo delším skokem, ale ne na tuhle
 * vzdálenost, je mrtvá zóna (skip člen).
 * Propagační člen dál odečte absorpci vrstvy D (George & Bradley, dB na skok ×
 * absMul, nejvýš absCap) a polární útlum (skoky nad auroraLat při Kp nad auroraKp,
 * auroraPerKp bodů na stupeň, nejvýš auroraCap).
 * Skip člen dál odečte útlum vzdáleností: lossMul × (20·log10(délka paprsku/refKm)
 * + hopLossDb na každý další skok), v mezích −lossCap až +nearBonusCap. refKm je
 * vzdálenost s nulovým útlumem; nastavená tak, aby se úroveň skóre proti dřívějšímu
 * modelu neposunula (hranice 50/68 zůstávají).
 * Laděno 11/2026 proti balkonovým snímkům (tools/calib.mjs) a 4 nocím z NightDX
 * (tools/memory_eval.mjs, sloupec „bez paměti"): AUC 0,65 → 0,70 na NightDX, balkon
 * beze zhoršení. Sezónní část (léto) stojí jen na fyzice a pár letních úlovcích
 * (tools/heard_check.mjs), měřená data jsou zatím jen z listopadu.
 *
 * dedup.sameSiteKm: dva záznamy s přesnou polohou (HFCC/AOKI, ne EiBi centroid)
 * na stejném kmitočtu ve stejnou chvíli do této vzdálenosti = jeden vysílací komplex
 * (HFCC „Sofia" 20 km od AOKI „Kostinbrod", „Beijing" 13 km od „Beijing 491")
 * = totéž vysílání pod dvěma názvy, ne rušitel.
 *
 * placeholderNames: HFCC rezervační sloty bez skutečného vysílatele („For new
 * organization" = brokerovaný čas, který reálně vysílá, ale program je v AOKI pod
 * pravým jménem). Při slučování dvojčat vyhraje pravé jméno; placeholder se nedrží
 * ani jako aka. V éteru ale zůstávají (QRM, dedup).
 *
 * blacklistDefault: skryté stanice (jen ze seznamu/radaru/oken; jako QRM se počítají
 * dál). Výchozí seznam skrývá jen osamocené HFCC placeholdery - čínské ani jiné
 * stanice ne. Uživatel si dopíše: vzor malými (cnr) = slovo/fráze v názvu, smí za ním
 * být číslo ("cnr" chytí "CNR1", ale "cri" ne "Radio Cristiana"); kód VELKÝMI (CHN)
 * = celá země (přesná shoda).
 *
 * memory: paměť příjmů (jen PWA; CLI ji nemá). Pozorování na témže kmitočtu ve stejnou
 * denní dobu (± windowH hodin UTC, váha klesá k okraji okna na polovinu) z téhož QTH
 * (do sameQthDeg stupňů) a ne starší než maxAgeDays posunou skóre o
 * amp·(slyšeno − n·baseline)/(n + k). baseline = obvyklý podíl slyšených pokusů, takže
 * jedno „neslyšeno" ubere málo a jedno „slyšeno" přidá hodně; k tlumí jediné pozorování.
 * heardMinDb = od kolika dB modulace nad šumem se nahrávka NightDX počítá jako slyšená.
 * Paměť se učí zvlášť pro každý přijímač (pozorování nese klíč přijímače; cizí přijímač
 * první desítku spíš kazil).
 * Ověřeno na 4 nocích NightDX (11/2026) křížově po nocích: AUC 0,65 → 0,74.
 *
 * Formulový tvar (pořadí členů, MUF/skip/absorpce) je zrcadlený v obou jazycích;
 * zde žijí pouze čísla, která se reálně ladí.
 */
window.SCORING = {
  "base": 50,
  "clamp": { "min": 5, "max": 99 },
  "boundaries": { "hi": 68, "mid": 50 },
  "spaceWeatherDefault": { "sfi": 142, "kp": 2 },
  "rxBonus": { "pl330": 0, "airspy": 12, "ats4732": -6 },
  "weightsDefault": { "balcony": 1.0, "power": 1.2, "skip": 1.0, "prop": 1.5 },
  "balcony": { "amp": 25 },
  "takeoff": { "altDivM": 1000, "altCap": 1.5, "farDistKm": 3500, "farMul": 15, "nearMul": 5 },
  "beam": { "nearDeg": 45, "midDeg": 110, "nearBonus": 8, "midBonus": 0, "farPenalty": -10 },
  "antenna": {
    "whip": [[5000, -18], [9000, -2], [15000, 10], [999999, 6]],
    "wire": [[5000, 8], [10000, 12], [18000, 4], [999999, 0]],
    "youloop": [[7000, -15], [15000, -6], [999999, -4]],
    "youloopAirspyBonus": 14
  },
  "power": { "centerKw": 100, "mul": 14 },
  "iono": {
    "maxHopKm": 3500, "layerKm": 320, "minElevDeg": 3,
    "dayBase": 7.5, "dayFlux": 6.0, "nightBase": 3.0, "nightFlux": 2.5, "nightFloor": 1.5,
    "seasonSummer": 2.5, "seasonWinter": 1.0, "eveFrac": 0.55, "decayH": 7, "lagH": 0, "smoothFromDeg": -18, "smoothToDeg": 14,
    "polarMul": 0.8, "equatorDayBoost": 0.15, "stormKp": 4, "stormDrop": 0.05,
    "mufSigma": 0.1, "mufPenalty": 45,
    "absMul": 0.5, "absCap": 45,
    "auroraLat": 55, "auroraKp": 3, "auroraPerKp": 4, "auroraCap": 20,
    "refKm": 3200, "lossMul": 1.2, "hopLossDb": 2, "lossCap": 60, "nearBonusCap": 12
  },
  "qrm": { "coChannel": -25, "adjacent": -8, "adjacentBoth": -16, "loopHalves": true,
    "minInterfererScore": 45, "louderMargin": 3 },
  "dedup": { "sameSiteKm": 30 },
  "memory": { "amp": 50, "baseline": 0.2, "k": 0.7, "windowH": 3, "maxAgeDays": 120,
    "sameQthDeg": 0.5, "heardMinDb": 4 },
  "placeholderNames": ["for new organization", "new organization", "disaster relief", "unknown"],
  "blacklistDefault": ["for new organization", "new organization", "disaster relief", "unknown"]
};
