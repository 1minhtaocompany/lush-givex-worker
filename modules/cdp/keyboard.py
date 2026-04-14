"""Keyboard helpers: per-character typing with adjacent-key typo simulation."""
import logging
import time

_log = logging.getLogger(__name__)
_ADJACENT = {
    'a':'sqwz','b':'vghn','c':'xdfv','d':'erfcs','e':'rdsw','f':'rtgvd','g':'tyhbf',
    'h':'yujng','i':'uojk','j':'uikmh','k':'iolmj','l':'opk','m':'nkj','n':'bhjm',
    'o':'iplk','p':'ol','q':'wa','r':'etdf','s':'wedaz','t':'ryfg','u':'yhij',
    'v':'cfgb','w':'qase','x':'zsdc','y':'tugi','z':'asx',
    '0':'9','1':'2','2':'13','3':'24','4':'35','5':'46','6':'57','7':'68','8':'79','9':'80',
}
_BACKSPACE = '\b'


def adjacent_char(char, rnd):
    """Return a random adjacent QWERTY key for *char*, or *char* if none."""
    n = _ADJACENT.get(char.lower(), "")
    return rnd.choice(n) if n else char


def type_value(element, value, rnd, *, typo_rate=0.0, delays=None, strict=False):
    """Type *value* per-character; correction cycle: wrong key→hesitation→backspace→correct."""
    result = {"typed_chars": 0, "typos_injected": 0, "corrections_made": 0, "mode": "per_char"}
    _warn = _log.warning if strict else _log.debug
    try:
        element.clear()
    except Exception:
        _log.debug("type_value: clear skipped", exc_info=True)
    for i, char in enumerate(value):
        d = delays[i] if (delays and i < len(delays)) else 0.05
        if typo_rate > 0 and rnd.random() < typo_rate:
            w = adjacent_char(char, rnd)
            if w != char:
                try:
                    element.send_keys(w)
                    result["typos_injected"] += 1
                except Exception:
                    _warn("type_value: typo failed for %r", w)
                time.sleep(max(0.08, d * 1.5))
                try:
                    element.send_keys(_BACKSPACE)
                    result["corrections_made"] += 1
                except Exception:
                    _log.debug("type_value: backspace skipped", exc_info=True)
                _log.debug("type_value: typo char=%r wrong=%r", char, w)
        try:
            element.send_keys(char)
            result["typed_chars"] += 1
        except Exception:
            _warn("type_value: char failed for %r", char)
        if d > 0:
            time.sleep(d)
    _log.debug("type_value: chars=%d typos=%d corrections=%d",
               result["typed_chars"], result["typos_injected"], result["corrections_made"])
    return result
