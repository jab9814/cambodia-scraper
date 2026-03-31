# cambodia-scraper

Scraper en Python para extraer datos de marcas registradas desde el portal de propiedad intelectual de Camboya. [Digitalip](https://digitalip.cambodiaip.gov.kh/en/trademark-search)

## Indice

- [Instalación y ejecución](#instalación-y-ejecución)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Información extraída](#información-extraída)
- [Registro de ejecución del script](#registro-de-ejecución-del-script)
- [Modos de operación de extracción de los filing numbers](#modos-de-operación-de-extracción-de-los-filing-numbers)
- [Proceso de pensamiento](#proceso-de-pensamiento)
  - [Investigación del sitio](#investigación-del-sitio)
  - [Decisiones técnicas](#decisiones-técnicas)
- [Tiempo real invertido](#tiempo-real-invertido)
- [Autor](#autor)

## Instalación y ejecución

**Requisitos:** `Python 3.10+`

El siguiente proceso es para clonar el repositorio y crear el entorno virtual. Se puede realizar con WSL y Ubuntu

```bash
# Clonar el repositorio
git clone https://github.com/jab9814/cambodia-scraper.git
cd cambodia-scraper

# Crear y activar el entorno virtual
python -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar navegador de Playwright
playwright install chromium

# Ejecutar
python scraper.py
```

## Estructura del proyecto

```bash
cambodia-scraper/
  ├──  scraper.py          # Lógica principal y punto de entrada
  ├──  utils.py            # Funciones de utilidad (guardar archivos, logging)
  ├──  constants.py        # Enums y constantes de configuración
  ├──  requirements.txt
  ├──  output/             # Archivos generados
  └──  logs/               # Archivo de log
```

## Información extraída

Los archivos `html` y `jpg` descargados se almacenan en la carpeta [output](output/) de acuerdo al valor del filing numbers:

``` bash
output/
    trademarks.json         # Datos extraídos de todas las marcas procesadas
    KH4963312_1.html        # Página de detalle
    KH4963312_2.jpg         # Imagen de la marca
    ...
```

Durante la extracción de la data, se creará un archivo json `trademarks.json`, el cual contendrá información ofrecida por la API de la fuente, como también la key `scraped_status` con indicación booleana si se logró descargar el archivo html y jpg correspondiente al FILING NUMBER

``` json
[
  {
    "id": "KHT201983498",
    "number": "KH/83498/19 (04-01-2019)",
    "application_date": "04-01-2019",
    "type_of_mark": "Combined",
    "title": "FORCE",
    "owner": "TIFORCE INTERNATIONAL CO., LTD.",
    "address": " No. 650AB, Street 271, Sangkat Phsar Deum Thkov, Khan Chamcarmon,\nPhnom Penh",
    "status": "Active (04-06-2020)",
    "representative": "N/A",
    "scraped_status": {
      "html": true,
      "image": true
    }
  },
  ...
]
```

## Registro de ejecución del script

La ejecución del código se puede visualizar mediante consola como en el archivo `scraper.log` ubicado en la carpeta [logs](/logs/).

---

## Modos de operación de extracción de los filing numbers

El scraper tiene dos modos configurable en [constants.py](/constants.py):

```python
ACTIVE_MODE = ScrapeMode.LIST  # Procesa los filing numbers de FILING_NUMBERS minimos requeridos en la prueba 
ACTIVE_MODE = ScrapeMode.ALL   # Pagina la API hasta MAX_RECORDS registros
```

- Sí se desea extraer los `filing numbers` minimos indicados en la prueba, se mantiene descomentado `ACTIVE_MODE = ScrapeMode.LIST`
- Sí se desea extraer los `filing numbers` ofrecidos en la fuente, se mantiene descomentado `ACTIVE_MODE = ScrapeMode.ALL`

En el modo `ScrapeMode.ALL` es necesario controlar el numero de registros a descargar, ya que la fuente ofrece mas de 150 mil resultados. Se controlan mediante dos parámetros:

```python
MAX_RECORDS = 10  # Numero de registros final que se desea obtener
PER_PAGE = 2     # Numero de registros a extraer por página de la API
```

- `MAX_RECORDS`: El usuario indicará la cantidad final de registros que desea descargar
- `PER_PAGE`: El usuario indicará la cantidad de registros que desea descargar por cada pagina que recorre

---

## Proceso de pensamiento

### Investigación del sitio

El portal de Cambodia IP es una SPA que carga contenido dinámicamente. Al inspeccionar las llamadas de red con DevTools se descubrió:

- La búsqueda se realiza mediante `POST /api/v1/web/trademark-search` con un body JSON que incluye el término de búsqueda, filtros y paginación.
- Cada resultado incluye un `id` interno (ej: `KHT201249633`) y un `file_type` que permiten construir la URL de detalle directamente.
- La URL de detalle sigue el patrón `/en/trademark-search/trademark-detail?afnb={id}&mdftyp={file_type}`.
- Las imágenes se sirven desde `/trademark-detail-logo/{id}?type=ts_logo_detail_screen` y requieren cookies de sesión activas para descargarse.

### Decisiones técnicas

**Playwright solo para cookies y HTML de detalle**

La página de detalle es una SPA que renderiza el contenido vía JavaScript, por lo que necesita un browser real para obtener el HTML completo. Sin embargo, Playwright se usa de forma mínima: una sola vez al inicio para obtener las cookies de sesión, y luego por cada página de detalle. Todo lo demás (búsqueda en la API e imágenes) se resuelve con httpx, que es más liviano y rápido.

**httpx para búsqueda e imágenes**

Una vez obtenidas las cookies con Playwright, httpx las reutiliza en todas las llamadas siguientes. Esto evita lanzar un browser para cada operación y reduce significativamente el uso de recursos.

**Procesamiento en paralelo**

Se usa `asyncio.gather` para procesar múltiples filing numbers de forma concurrente, reduciendo el tiempo total de ejecución.

**Guardado incremental del JSON**

El archivo `trademarks.json` se actualiza a medida que cada marca se procesa, en lugar de esperar a que termine todo el scraping. Esto garantiza que si la ejecución se interrumpe, los registros ya procesados no se pierden. Cada registro incluye un campo `scraped_status` que indica si el HTML y la imagen fueron obtenidos exitosamente.

**Reintentos con tenacity**

Todas las operaciones de red (cookies, búsqueda, HTML, imagen) tienen reintentos automáticos ante fallos transitorios. Si una operación falla después de 3 intentos, se loguea el error y el scraper continúa con el siguiente registro sin detenerse.

**Constantes con Enum**

Las URLs, modos de operación y parámetros de imagen se definen como `Enum` en `constants.py`, evitando strings sueltos en el código y facilitando futuros cambios.

---

## Tiempo real invertido

Aproximadamente **X horas**, distribuidas en:

- Investigación del sitio y análisis de las llamadas de red: ~X horas
- Implementación del scraper: ~X horas
- Pruebas y ajustes: ~X horas

## Autor

- 🖥️ Desarrollado por: [jab9814](https://github.com/jab9814)
