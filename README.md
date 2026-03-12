# Social Scrapp - Lead Finder (Selenium + BeautifulSoup + SQLite + Dashboard)

Proyecto en Python 3.11+ para detectar nuevos leads desde una sesión manual ya iniciada en:
- Facebook
- Instagram
- LinkedIn
- Pinterest
- Reddit
- Twitter/X

Incluye:
- Scraping conservador con Selenium + BeautifulSoup
- Enriquecimiento (clasificación + señales + scoring)
- Exportación CSV/JSON
- Base de datos SQLite completa (leads + histórico de runs)
- Dashboard interactivo con botones de acción y gráficos

> **Importante**
> - Este proyecto **no** evade captchas, 2FA, bloqueos ni rate limits.
> - Solo extrae información visible públicamente o visible para tu cuenta autenticada.

## Estructura

```text
project/
  main.py
  dashboard.py
  config.py
  requirements.txt
  .env.example
  README.md
  scrapers/
  parsers/
  models/
  utils/
  output/
    leads.csv
    leads.json
    leads.db
  debug_html/
```

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Configuración (.env)

Variables principales:
- `CHROME_PROFILE_PATH`
- `USER_DATA_DIR`
- `HEADLESS`
- `MAX_PROFILES_PER_PLATFORM`
- `MAX_RESULTS_PER_QUERY`
- `MIN_DELAY`, `MAX_DELAY`
- `OUTPUT_DIR`
- `SAVE_DEBUG_HTML`
- `SQLITE_DB_PATH` (ej. `output/leads.db`)
- keywords por plataforma

## Ejecutar scraping

```bash
python main.py
```

También puedes limitar plataformas desde CLI:

```bash
python main.py --platforms instagram,linkedin,twitter
```

Salidas:
- `output/leads.csv`
- `output/leads.json`
- `output/leads.db`
- `debug_html/*.html`

## Ejecutar dashboard

```bash
streamlit run dashboard.py
```

> Nota: el formulario de credenciales del dashboard es opcional y actualmente se pasa como payload de configuración para trazabilidad; el flujo sigue usando sesión manual ya iniciada en navegador.

### Funciones del dashboard
- Selector de **redes a scrapear** para la próxima corrida.
- Formulario opcional de **usuario/password por red**.
- Botón **Refrescar datos**.
- Botón **Ejecutar scraping ahora** (lanza `python main.py --platforms ... --credentials-file ...`).
- Filtros por plataforma, tipo de lead y score mínimo.
- KPIs de calidad (cantidad, score medio, con email, con website).
- Gráficos:
  - Leads por plataforma
  - Distribución por tipo de lead
  - Histograma de score
  - Top países
- Tabla interactiva de leads.
- Botones para descargar CSV/JSON filtrado.
- Tabla de histórico de ejecuciones (`scraping_runs`).

## Base de datos SQLite

Tablas:
- `scraping_runs`: inicio/fin, estado, totales por ejecución.
- `leads`: datos completos de lead + score + raw_data + timestamps.

El guardado se hace con upsert y actualización de información más completa.

## Cómo adaptar selectores cuando cambia el DOM

Cada scraper define constantes `*_SELECTORS` al inicio del archivo.

Flujo recomendado:
1. Activar `SAVE_DEBUG_HTML=true`.
2. Ejecutar scraping.
3. Inspeccionar HTML en `debug_html/`.
4. Ajustar selectores en `scrapers/*_scraper.py`.
5. Revalidar.
