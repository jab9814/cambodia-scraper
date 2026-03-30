import asyncio
import logging
import httpx
from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from utils import save_html, save_image, save_json, ensure_output_dir, setup_logging
from constants import URL, ImageType, FILING_NUMBERS, ScrapeMode, MAX_RECORDS, PER_PAGE, ACTIVE_MODE, build_search_payload

setup_logging()
logger = logging.getLogger(__name__)


async def get_session_cookies() -> dict:
    """Abre el sitio con Playwright y retorna las cookies de sesión."""
    logger.info("Obteniendo cookies de sesión con Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(f"{URL.BASE.value}/en/trademark-search", wait_until="networkidle", timeout=30000)
        cookies = await context.cookies()
        await browser.close()

    return {c["name"]: c["value"] for c in cookies}


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(httpx.HTTPError))
async def search_trademark(client: httpx.AsyncClient, filing_number: str) -> dict | None:
    """Busca un filing number y retorna el registro con id y file_type."""
    logger.info(f"Buscando: {filing_number}")
    response = await client.post(URL.SEARCH, json=build_search_payload(filing_number))
    response.raise_for_status()
    results = response.json()["data"]["data"]

    if not results:
        logger.warning(f"No se encontraron resultados para: {filing_number}")
        return None

    # Buscar el match exacto por filing number en el campo "number"
    base = filing_number.lower()
    for item in results:
        if item.get("number", "").lower().startswith(base):
            return item

    logger.warning(f"No se encontró match exacto para: {filing_number}")
    return None


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
async def get_detail_html(trademark_id: str, file_type: str) -> str:
    """Carga la página de detalle con Playwright y retorna el HTML renderizado."""
    url = f"{URL.BASE.value}{URL.DETAIL.value}?afnb={trademark_id}&mdftyp={file_type}"
    logger.info(f"Cargando detalle: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        html = await page.content()
        await browser.close()
    return html


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(httpx.HTTPError))
async def get_image(client: httpx.AsyncClient, trademark_id: str) -> bytes | None:
    """Descarga la imagen de la marca usando httpx con cookies de sesión."""
    url = f"{URL.IMAGE.value}/{trademark_id}"
    logger.info(f"Descargando imagen: {url}")
    response = await client.get(url, params={"type": ImageType.DETAIL_SCREEN.value})

    if response.status_code == 404:
        logger.warning(f"Imagen no disponible para: {trademark_id}")
        return None

    response.raise_for_status()
    return response.content


async def scrape(client: httpx.AsyncClient, result: dict) -> dict | None:
    """Orquesta el scraping completo para un resultado de la API."""
    trademark_id = result["id"]
    file_type = result["file_type"]
    filing_number = result["number"].split(" ")[0]

    html = await get_detail_html(trademark_id, file_type)
    save_html(html, filing_number)

    if result.get("logo"):
        image = await get_image(client, trademark_id)
        if image:
            save_image(image, filing_number)
    else:
        logger.info(f"La marca {filing_number} no tiene imagen, se omite.")

    return result


async def scrape_list(client: httpx.AsyncClient) -> list[dict]:
    """Modo lista: procesa los filing numbers de FILING_NUMBERS."""
    async def _search_and_scrape(filing_number: str) -> dict | None:
        result = await search_trademark(client, filing_number)
        if not result:
            return None
        return await scrape(client, result)

    results = await asyncio.gather(*[_search_and_scrape(fn) for fn in FILING_NUMBERS])
    return [r for r in results if r is not None]


async def scrape_all(client: httpx.AsyncClient) -> list[dict]:
    """Modo completo: pagina la API hasta obtener MAX_RECORDS registros."""
    records = []
    page = 1

    while len(records) < MAX_RECORDS:
        remaining = MAX_RECORDS - len(records)
        per_page = min(PER_PAGE, remaining)
        payload = build_search_payload("", page=page, per_page=per_page)
        response = await client.post(URL.SEARCH.value, json=payload)
        response.raise_for_status()
        batch = response.json()["data"]["data"]
        if not batch:
            break
        records.extend(batch)
        page += 1

    logger.info(f"Total registros obtenidos: {len(records)}")
    results = await asyncio.gather(*[scrape(client, r) for r in records])
    return [r for r in results if r is not None]


async def main() -> None:
    ensure_output_dir()
    cookies = await get_session_cookies()

    async with httpx.AsyncClient(base_url=URL.BASE.value, cookies=cookies, timeout=30) as client:
        if ACTIVE_MODE == ScrapeMode.LIST:
            records = await scrape_list(client)
        else:
            records = await scrape_all(client)

    if records:
        save_json(records)

    logger.info("Scraping completado.")


if __name__ == "__main__":
    asyncio.run(main())
