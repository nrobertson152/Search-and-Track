"""Cosmetic Russian engraving for the Soviet command post.

Gameplay text (orders, radio, briefings, tooltips, the manual) stays in English;
what changes is the hardware: keycap legends, nameplates, lamp captions, CRT
legends and table headings are engraved in Russian, with an optional small
English translation strip ("ru+en", the default), Russian only ("ru") or
English only ("en").

Lookups take the English label used throughout the code (which also remains
the button's identity for tests and the tutorial highlighter) and return the
Russian legend. Labels ending in a variable part ("SCRAMBLE ON 4502",
"SALVO 2") are matched by their longest known prefix."""
from __future__ import annotations

RU: dict[str, str] = {
    # ---- console selector & displays
    "TRACKS": "ЦЕЛИ", "WEAPONS": "НАВЕДЕНИЕ", "MISSILES": "ЗРВ", "RADAR": "РТВ", "COMMS": "СВЯЗЬ",
    "INTEL": "РАЗВЕДКА", "STATUS": "ГОТОВНОСТЬ", "NETWORK": "МНЕМОСХЕМА",
    "SITUATION": "ПЛАНШЕТ", "BOARD": "ПЛАНШЕТ", "RADAR SCOPE": "ИКО", "SCOPE": "ИКО",
    "COVERAGE": "РЛ ПОЛЕ", "RAW": "ОТМЕТКИ", "ZONES": "РАЙОНЫ", "LABELS": "НАДПИСИ", "HISTORY": "СЛЕД",
    "RINGS": "КОЛЬЦА", "DN": "НИЖЕ", "UP": "ВЫШЕ", "RANGE": "МАСШТАБ", "MENU": "МЕНЮ", "II": "СТОП",
    # ---- identities (English labels from doctrine.ID_LABELS_EN)
    "OWN": "СВОЙ", "UNIDENTIFIED": "НЕОПОЗН.", "FOREIGN": "ЧУЖОЙ", "VIOLATOR": "НАРУШИТЕЛЬ",
    "TRAINING": "УЧЕБН.", "PROCESSING": "ОБРАБ.",
    # ---- track actions
    "HEIGHT (H)": "ВЫСОТА", "REPORT": "ДОКЛАД", "DROP": "СБРОС", "MERGE": "ОБЪЕДИН.", "CENTER": "ЦЕНТР",
    # ---- fighter control
    "INTERCEPT": "ПЕРЕХВАТ", "ID PASS": "ОПОЗНАТЬ", "SHADOW": "СОПРОВОД.", "CAP": "БАРРАЖ",
    "LEAD": "ПЕРЕСЕЧ.", "STERN": "ЗПС", "PURSUIT": "ПОГОНЯ", "SCRAMBLE ON": "ПОДЪЁМ НА",
    "SCRAMBLE (NO TARGET)": "ПОДЪЁМ", "RAISE ALERT +1": "ГОТОВНОСТЬ +1", "ASSIGN": "НАЦЕЛИТЬ",
    "INTCPT": "ПЕРЕХВАТ", "AUTO": "АВТОМАТ", "MANUAL": "РУЧНОЕ", "RTB": "ВОЗВРАТ",
    "HDG −15": "КУРС −15", "HDG +15": "КУРС +15", "ALT −": "ВЫСОТА −", "ALT +": "ВЫСОТА +",
    "BUSTER": "ФОРСАЖ", "GATE OFF": "ФОРСАЖ ВЫКЛ", "WPN FREE": "АТАКА РАЗР.", "WPN HOLD": "АТАКА ЗАПР.",
    "GUID. PT": "СМЕНА ПН", "ORDER RAMMING": "ТАРАН", "FORCE LANDING": "ПРИНУДИТЬ К ПОСАДКЕ", "LOCK-ON": "ЗАХВАТ",
    "WARNING SHOTS": "ПРЕДУПР. ОГОНЬ",
    # ---- requests to higher command
    "HOSTILE": "НАРУШИТЕЛЬ", "ENGAGE": "УНИЧТОЖИТЬ", "RAM": "ТАРАН", "WEAPONS TIGHT": "ОГОНЬ ОГРАН.",
    "WEAPONS FREE": "ОГОНЬ РАЗРЕШ.", "WEAPONS HOLD": "ОГОНЬ ЗАПРЕЩ.", "READINESS FULL": "БГ ПОЛНАЯ",
    # ---- SAM control
    "DESIGNATE": "ЦУ", "HOLD FIRE": "ЗАПРЕТ ОГНЯ", "RELEASE": "СНЯТЬ ЗАПРЕТ", "CANCEL": "ОТМЕНА",
    "SALVO": "ЗАЛП", "AUTO RE-ENG": "АВТ. ПОВТОР", "RE-ENG ON ORDER": "ПОВТОР ПО КОМ.",
    "BRING TO READINESS": "ПРИВЕСТИ В ГОТОВНОСТЬ",
    # ---- radar technical
    "MTI": "СДЦ", "IFF INTERR.": "НРЗ", "THRESHOLD": "ПОРОГ", "ANTENNA": "АНТЕННА", "FREQ CHANNEL": "ЧАСТОТА",
    "MAINT 30 MIN": "РЕГЛАМЕНТ 30 МИН", "REPAIR": "РЕМОНТ",
    # ---- comms & intel
    "ALL": "ВСЕ", "RADIO": "РАДИО", "VOICE": "ТЕЛЕФОН", "TELETYPE": "ТЕЛЕГРАФ", "ALERTS": "СИГНАЛЫ",
    "ACK ALL": "КВИТИРОВАТЬ", "BRIEFING": "ЗАДАЧА", "REPORTS": "СВОДКИ", "AIRCRAFT": "СИЛУЭТЫ",
    "TECH NOTES": "СПРАВКИ",
    # ---- status / positions
    "SURVEILLANCE": "ОБНАРУЖЕНИЕ", "IDENTIFICATION": "ОПОЗНАВАНИЕ", "HEIGHT": "ВЫСОТОМЕР", "TECHNICAL": "ТЕХНИКА",
    "SAVE (F5)": "ЗАПИСЬ", "LOAD (F9)": "ЗАГРУЗКА", "END SHIFT": "СДАТЬ СМЕНУ",
    # ---- menus & scenes
    "RESUME": "ПРОДОЛЖИТЬ", "SAVE": "ЗАПИСЬ", "LOAD": "ЗАГРУЗКА", "< PREV": "< ПРЕД.", "NEXT >": "СЛЕД. >",
    "OPERATOR'S MANUAL": "НАСТАВЛЕНИЕ",
    "SOUND": "ЗВУК", "END SHIFT → DEBRIEF": "СДАТЬ СМЕНУ", "QUIT TO TITLE": "ВЫХОД", "SETTINGS": "НАСТРОЙКИ",
    "TAKE THE WATCH >>": "ЗАСТУПИТЬ НА ДЕЖУРСТВО", "BACK": "НАЗАД", "SUMMARY": "ИТОГИ",
    "DETECTION & ID": "ОБНАРУЖЕНИЕ", "TIMELINE": "ХРОНОЛОГИЯ", "BACK TO TITLE": "В НАЧАЛО",
    "SAVE REPORT": "СОХРАНИТЬ", "BRIEFING >>": "ИНСТРУКТАЖ >>", "NEW SEED": "НОВАЯ СМЕНА", "QUIET": "СПОКОЙНО",
    "ROUTINE": "ОБЫЧНО", "BUSY": "НАПРЯЖЁННО", "CONTINUE": "ДАЛЕЕ", "NEXT": "ДАЛЕЕ", "AUTO-SLOW ON ALERTS": "ЗАМЕДЛЕНИЕ",
    "ON": "ВКЛ", "OFF": "ВЫКЛ",
    # ---- panel nameplates
    "SURVEILLANCE & IDENTIFICATION": "ЦЕЛИ", "COVERAGE ANALYSIS": "АНАЛИЗ РЛ ПОЛЯ",
    "AIRBASES & SQUADRONS": "АЭРОДРОМЫ И ПОЛКИ", "REQUESTS TO HIGHER AUTHORITY": "ЗАПРОСЫ НА КП",
    "TELEPHONE LINES": "ЛИНИИ СВЯЗИ", "AN/FSQ-7 DUPLEX": "AN/FSQ-7", "WEAPONS DIRECTION": "НАВЕДЕНИЕ ИСТРЕБИТЕЛЕЙ",
    "MISSILE CONTROL": "УПРАВЛЕНИЕ ЗРВ", "RADAR NETWORK & TECHNICAL": "РАДИОТЕХНИЧЕСКИЕ ВОЙСКА",
    "COMMUNICATIONS": "СВЯЗЬ", "INTELLIGENCE": "РАЗВЕДКА", "STATUS & LOGISTICS": "ГОТОВНОСТЬ И ОБЕСПЕЧЕНИЕ",
    "AFTER-ACTION REPORT": "РАЗБОР",
    "OBJECTIVES": "ЗАДАЧИ", "FORCES": "СИЛЫ И СРЕДСТВА", "POSITIONS (automation)": "РАСЧЁТ",
    "TIME": "ВРЕМЯ", "DISPLAY": "ИНДИКАЦИЯ", "CONSOLE": "ПУЛЬТ", "NET STATUS": "СОСТОЯНИЕ СЕТИ",
    # ---- annunciators / lamps
    "READY": "БГ", "FULL": "ПОЛНАЯ", "INCREASED": "ПОВЫШЕННАЯ", "CONSTANT": "ПОСТОЯННАЯ",
    "WPNS": "ОГОНЬ", "ACK": "КВИТ", "POWER": "СЕТЬ", "OVERLOAD": "ПЕРЕГРУЗКА", "ENABLED": "ВКЛ",
    "BRIGHTNESS": "ЯРКОСТЬ", "CONTRAST": "КОНТРАСТ", "MODE": "РЕЖИМ РАБОТЫ", "FOCUS": "ФОКУС",
    "SWEEP": "РАЗВЁРТКА", "ALARM": "ТРЕВОГА", "LINE": "ЛИНИЯ", "FAULT": "НЕИСПР.", "OK": "НОРМА",
}

# Table headings (CRT legends): Russian with the English as a tooltip.
HEAD: dict[str, str] = {
    "TRK": "№ Ц", "IDENT": "ПРИНАДЛ.", "ALT": "ВЫС", "SPD": "СКОР", "HDG": "КУРС", "Q": "К", "IFF": "ОПОЗН",
    "AGE": "ВОЗР", "NOTE": "ПРИМЕЧ.", "FLIGHT": "ГРУППА", "TYPE": "ТИП", "STATE": "СОСТ.", "TASK": "ЗАДАЧА",
    "TGT": "ЦЕЛЬ", "FUEL": "ТОПЛ.", "SITE": "ПОЗИЦИЯ", "MSL": "РАК.", "SQUADRON": "ПОЛК", "READY": "ГОТОВ",
    "RADAR": "РЛС", "LINK": "ЛИНИЯ", "DELAY": "ЗАДЕРЖ.", "TIME": "ВРЕМЯ", "FROM": "ОТ КОГО", "RANGE": "ДАЛЬН.",
    "Pd": "Pобн", "SINR": "С/Ш", "LIMIT / REASON": "ОГРАНИЧЕНИЕ", "STATUS": "СОСТОЯНИЕ", "UNIT": "ЧАСТЬ",
}

# Hint text for keys whose English is not obvious from the label itself.
_STRIP_OVERRIDE = {"II": "PAUSE", "DN": "DOWN", "ЗПС": "STERN"}


def ru(text: str) -> str | None:
    """Russian legend for an English label, or None if there is none."""
    if not text:
        return None
    hit = RU.get(text)
    if hit is not None:
        return hit
    # longest known prefix followed by a variable part ("SCRAMBLE ON 4502", "SALVO 2", "ACK ALL (3)")
    best = ""
    for k in RU:
        if len(k) > len(best) and text.startswith(k) and len(text) > len(k) and text[len(k)] in " (:!":
            rest = text[len(k):].strip()
            if any(ch.isdigit() for ch in rest) or rest in ("—", "-") or rest[:1] in "(:!" or rest in RU:
                best = k
    if best:
        rest = text[len(best):]
        if rest.startswith(": "):
            v = rest[2:]
            return RU[best] + ": " + RU.get(v, v)
        return RU[best] + rest
    # keys carrying a function-key hint: "TRACKS F1" -> "ЦЕЛИ"
    head, _, tail = text.rpartition(" ")
    if head and tail[:1] == "F" and tail[1:].isdigit() and head in RU:
        return RU[head]
    return None


def head(text: str, faction: str, mode: str = "ru+en") -> str:
    if faction != "USSR" or mode == "en":
        return text
    return HEAD.get(text, text)


def legend(text: str, faction: str, mode: str = "ru+en") -> tuple[str, str]:
    """(main legend, translation strip) for a control label."""
    if faction != "USSR" or mode == "en":
        return text, ""
    r = ru(text)
    if r is None:
        return text, ""
    if mode == "ru":
        return r, ""
    return r, _STRIP_OVERRIDE.get(text, text)
