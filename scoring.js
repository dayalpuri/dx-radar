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
 * muf: noční MUF = const + sfiMul·SFI + seasonNight·(deklinace/23,44°); den přidá
 * dayBoost (plynule podle osvětlení středu trasy mezi smoothFromDeg a smoothToDeg;
 * −18° = astronomický soumrak, kdy zhasne vrstva F2 ve ~300 km). seasonNight: letní
 * noční F2 vrstva nestihne zrekombinovat (krátká noc, vyšší noční foF2), zimní ano -
 * v létě tedy noční MUF o několik MHz výš, v zimě níž (v den je člen nulový).
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
  "muf": { "const": 4.5, "sfiMul": 0.09, "dayBoost": 15, "seasonNight": 5,
    "smoothFromDeg": -18, "smoothToDeg": 14 },
  "prop": {
    "aboveMufPenalty": -35,
    "nearMufPenalty": -14,
    "mufMarginKHz": 3000,
    "auroralKp": 5,
    "auroralFromDeg": 300,
    "auroralToDeg": 60,
    "auroralPenalty": -20
  },
  "dayAbsorption": { "freqCeilKHz": 10000, "maxPenalty": 40 },
  "skip": {
    "pivotMHz": 7,
    "slopeKmPerMHz": 300,
    "floorCapKm": 4000,
    "nearPenaltyMax": 20,
    "farStartKm": 3000,
    "farDivKm": 2000,
    "farPenaltyMul": 8
  },
  "qrm": { "coChannel": -25, "adjacent": -8, "adjacentBoth": -16, "loopHalves": true,
    "minInterfererScore": 45, "louderMargin": 3 },
  "dedup": { "sameSiteKm": 30 },
  "placeholderNames": ["for new organization", "new organization", "disaster relief", "unknown"],
  "blacklistDefault": ["for new organization", "new organization", "disaster relief", "unknown"]
};
