import logging
import json
from pathlib import Path
from constants import JSON_FIELDS


LOGS_DIR = Path("logs")
OUTPUT_DIR = Path("output")
logger = logging.getLogger(__name__)


def setup_logging() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "scraper.log", encoding="utf-8")
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers
    )


def build_filename(filing_number: str) -> str:
    """'KH/49633/12' → 'KH4963312'"""
    return filing_number.replace("/", "")


def save_html(content: str, filing_number: str) -> None:
    filename = build_filename(filing_number)
    path = OUTPUT_DIR / f"{filename}_1.html"
    path.write_text(content, encoding="utf-8")
    logger.info(f"HTML guardado: {path}")


def save_image(content: bytes, filing_number: str) -> None:
    filename = build_filename(filing_number)
    path = OUTPUT_DIR / f"{filename}_2.jpg"
    path.write_bytes(content)
    logger.info(f"Imagen guardada: {path}")


def save_json(record: dict) -> None:
    path = OUTPUT_DIR / "trademarks.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    data.append({field: record.get(field) for field in JSON_FIELDS} | {"scraped_status": record.get("scraped_status")})
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"[{record.get('number', '').split(' ')[0]}] Registro guardado en JSON.")


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
