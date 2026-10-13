"""Live measurements kept in memory. Module-level state is shared by every browser session in the same
Streamlit server process and is reset when the server restarts, so the screen labels it 'since the server started'."""
_scoring_ms = []


def record_scoring_time(ms):
    _scoring_ms.append(float(ms))
    del _scoring_ms[:-500]          # keep the most recent 500 only


def scoring_stats():
    if not _scoring_ms:
        return None
    return {"count": len(_scoring_ms), "avg": sum(_scoring_ms) / len(_scoring_ms),
            "max": max(_scoring_ms), "last": _scoring_ms[-1]}