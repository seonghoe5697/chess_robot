"""
core/engine.py
Stockfish 엔진 로딩과 경로 설정을 한 곳에서 관리합니다.
모든 GUI·앱 파일은 여기서 엔진을 가져다 씁니다.
"""

import sys
import platform
import chess.engine

# ── 경로 설정 ──────────────────────────────────────────────────────────────
def _default_stockfish_path() -> str:
    """OS에 맞는 기본 Stockfish 실행 파일 경로를 반환합니다."""
    if platform.system() == "Windows":
        return "stockfish-windows-x86-64.exe"
    elif platform.system() == "Darwin":   # macOS
        return "stockfish"
    else:                                 # Linux (라즈베리파이 포함)
        return "stockfish"

STOCKFISH_PATH: str = _default_stockfish_path()


# ── 엔진 팩토리 ────────────────────────────────────────────────────────────
def create_engine(
    path: str = STOCKFISH_PATH,
    elo: int = 2850,
    limit_strength: bool = True,
) -> chess.engine.SimpleEngine:
    """
    Stockfish 엔진 인스턴스를 생성해서 반환합니다.

    Parameters
    ----------
    path            : Stockfish 실행 파일 경로
    elo             : UCI_Elo 설정값 (강도 조절)
    limit_strength  : UCI_LimitStrength 활성화 여부

    Returns
    -------
    chess.engine.SimpleEngine

    Raises
    ------
    FileNotFoundError : 실행 파일이 없을 때
    RuntimeError      : 엔진 실행 실패 시
    """
    try:
        engine = chess.engine.SimpleEngine.popen_uci(path)
        engine.configure({
            "UCI_LimitStrength": limit_strength,
            "UCI_Elo": elo,
        })
        return engine
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Stockfish 실행 파일을 찾을 수 없습니다: '{path}'\n"
            "경로를 확인하거나 STOCKFISH_PATH를 직접 지정하세요."
        )
    except Exception as e:
        raise RuntimeError(f"엔진 실행 중 오류: {e}")


def safe_quit(engine: chess.engine.SimpleEngine) -> None:
    """엔진 프로세스를 안전하게 종료합니다. 예외는 무시합니다."""
    try:
        engine.quit()
    except Exception:
        pass
