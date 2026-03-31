import asyncio
import logging
import math
import httpx
from playwright.async_api import async_playwright, Browser
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type, RetryError
from utils import save_html, save_image, save_json, ensure_output_dir, setup_logging, OUTPUT_DIR
from constants import URL, ImageType, FILING_NUMBERS, ScrapeMode, MAX_RECORDS, PER_PAGE, ACTIVE_MODE, build_search_payload

setup_logging()
logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), retry=retry_if_exception_type(Exception))
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
    return {cookie["name"]: cookie["value"] for cookie in cookies}


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(httpx.HTTPError))
async def search_trademark(client: httpx.AsyncClient, filing_number: str) -> dict | None:
    """Busca un filing number y retorna el registro con id y file_type."""
    logger.info(f"[{filing_number}] Buscando en la API...")
    response = await client.post(URL.SEARCH, json=build_search_payload(filing_number))
    response.raise_for_status()
    results = response.json()["data"]["data"]

    if not results:
        logger.warning(f"[{filing_number}] No se encontraron resultados.")
        return None

    base = filing_number.lower()
    for item in results:
        if item.get("number", "").lower().startswith(base):
            logger.info(f"[{filing_number}] Encontrado: {item['id']}")
            return item

    logger.warning(f"[{filing_number}] No se encontró match exacto.")
    return None


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
async def get_detail_html(browser: Browser, trademark_id: str, file_type: str, filing_number: str) -> str:
    """Carga la página de detalle con Playwright y retorna el HTML renderizado."""
    url = f"{URL.BASE.value}{URL.DETAIL.value}?afnb={trademark_id}&mdftyp={file_type}"
    logger.info(f"[{filing_number}] Cargando HTML de detalle...")
    page = await browser.new_page()
    await page.goto(url, wait_until="networkidle", timeout=30000)
    html = await page.content()
    await page.close()
    logger.info(f"[{filing_number}] HTML obtenido correctamente.")
    return html


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(httpx.HTTPError))
async def get_image(client: httpx.AsyncClient, trademark_id: str, filing_number: str) -> bytes | None:
    """Descarga la imagen de la marca usando httpx con cookies de sesión."""
    logger.info(f"[{filing_number}] Descargando imagen...")
    response = await client.get(f"{URL.IMAGE.value}/{trademark_id}", params={"type": ImageType.DETAIL_SCREEN.value})

    if response.status_code == 404:
        logger.warning(f"[{filing_number}] Imagen no disponible.")
        return None

    response.raise_for_status()
    logger.info(f"[{filing_number}] Imagen obtenida correctamente.")
    return response.content


async def scrape(client: httpx.AsyncClient, browser: Browser, result: dict) -> None:
    """Orquesta el scraping completo para un resultado de la API."""
    trademark_id = result["id"]
    file_type = result["file_type"]
    filing_number = result["number"].split(" ")[0]
    scraped_status = {"html": False, "image": False}

    try:
        html = await get_detail_html(browser, trademark_id, file_type, filing_number)
        save_html(html, filing_number)
        scraped_status["html"] = True
    except RetryError:
        logger.error(f"[{filing_number}] No se pudo obtener el HTML después de 3 intentos.")

    if result.get("logo"):
        try:
            image = await get_image(client, trademark_id, filing_number)
            if image:
                save_image(image, filing_number)
                scraped_status["image"] = True
        except RetryError:
            logger.error(f"[{filing_number}] No se pudo descargar la imagen después de 3 intentos.")
    else:
        logger.info(f"[{filing_number}] Sin imagen asociada, se omite.")

    result["scraped_status"] = scraped_status
    save_json(result)


async def search_and_scrape(client: httpx.AsyncClient, browser: Browser, filing_number: str) -> None:
    """Busca un filing number y ejecuta el scraping completo."""
    try:
        result = await search_trademark(client, filing_number)
    except RetryError:
        logger.error(f"[{filing_number}] No se pudo obtener datos de la API después de 3 intentos.")
        return
    if result:
        await scrape(client, browser, result)


async def scrape_list(client: httpx.AsyncClient, browser: Browser) -> None:
    """Modo lista: procesa los filing numbers de FILING_NUMBERS."""
    await asyncio.gather(*[search_and_scrape(client, browser, filing_number) for filing_number in FILING_NUMBERS])


async def scrape_all(client: httpx.AsyncClient, browser: Browser) -> None:
    """Modo completo: pagina la API hasta obtener MAX_RECORDS registros."""
    total_pages = math.ceil(MAX_RECORDS / PER_PAGE)
    records = []

    for page in range(1, total_pages + 1):
        per_page = min(PER_PAGE, MAX_RECORDS - len(records))
        payload = build_search_payload("", page=page, per_page=per_page)
        response = await client.post(URL.SEARCH.value, json=payload)
        response.raise_for_status()
        batch = response.json()["data"]["data"]
        if not batch:
            logger.warning(f"Página {page} sin resultados, deteniendo.")
            break
        records.extend(batch)
        logger.info(f"Página {page}/{total_pages} obtenida: {len(batch)} registros.")

    logger.info(f"Total registros obtenidos: {len(records)}")
    await asyncio.gather(*[scrape(client, browser, record) for record in records])


async def main() -> None:
    ensure_output_dir()
    (OUTPUT_DIR / "trademarks.json").unlink(missing_ok=True)

    try:
        cookies = await get_session_cookies()
    except RetryError:
        logger.error("No se pudo obtener la sesión después de 3 intentos. Verifique su conexión o el estado del sitio.")
        return

    logger.info("Cookies de sesión obtenidas.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        async with httpx.AsyncClient(base_url=URL.BASE.value, cookies=cookies, timeout=30) as client:
            if ACTIVE_MODE == ScrapeMode.LIST:
                logger.info("Iniciando modo LIST... Busqueda de registros especificados.")
                await scrape_list(client, browser)
            else:
                logger.info("Iniciando modo ALL... Busqueda de todos los registros disponibles en la API.")
                await scrape_all(client, browser)
        await browser.close()

    logger.info("Scraping completado.")


if __name__ == "__main__":
    asyncio.run(main())
