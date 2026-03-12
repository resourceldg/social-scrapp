# Social Scrapp - Lead Finder (Selenium + BeautifulSoup)

Proyecto en Python 3.11+ para detectar nuevos leads desde una sesión manual ya iniciada en:
- Facebook
- Instagram
- LinkedIn
- Pinterest
- Reddit
- Twitter/X

> **Importante**
> - Este proyecto **no** evade captchas, 2FA, bloqueos ni rate limits.
> - Solo extrae información visible públicamente o visible para tu cuenta autenticada.
> - Usa navegación conservadora, delays aleatorios y límites por query/plataforma.

## Estructura

```text
project/
  main.py
  config.py
  requirements.txt
  .env.example
  README.md
  scrapers/
    __init__.py
    instagram_scraper.py
    facebook_scraper.py
    linkedin_scraper.py
    pinterest_scraper.py
    reddit_scraper.py
    twitter_scraper.py
  parsers/
    __init__.py
    lead_parser.py
  models/
    __init__.py
    lead.py
  utils/
    __init__.py
    browser.py
    helpers.py
    classifiers.py
    scoring.py
    exporters.py
    dedupe.py
    logging_setup.py
  output/
    leads.csv
    leads.json
  debug_html/
```

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Configuración

Edita `.env`:
- Configura `USER_DATA_DIR` y/o `CHROME_PROFILE_PATH` para reutilizar tu sesión de Chrome.
- Ajusta límites:
  - `MAX_PROFILES_PER_PLATFORM`
  - `MAX_RESULTS_PER_QUERY`
  - `MIN_DELAY`, `MAX_DELAY`
- Ajusta keywords por plataforma.

## Ejecución

1. Verifica que tu perfil de Chrome tenga sesión iniciada en las plataformas objetivo.
2. Ejecuta:

```bash
python main.py
```

3. Resultados:
- `output/leads.csv`
- `output/leads.json`
- HTML crudo para depuración en `debug_html/`

## Cómo adaptar selectores cuando cambia el DOM

Cada scraper define constantes `*_SELECTORS` al inicio del archivo.

Ejemplo:
- `scrapers/instagram_scraper.py` -> `INSTAGRAM_SELECTORS`
- `scrapers/linkedin_scraper.py` -> `LINKEDIN_SELECTORS`

Flujo recomendado:
1. Activa `SAVE_DEBUG_HTML=true`.
2. Ejecuta el scraper.
3. Abre el HTML guardado en `debug_html/`.
4. Inspecciona nuevos atributos de nodos de resultados.
5. Actualiza lista de selectores (mantén varios fallback selectors).
6. Vuelve a correr y valida.

## Pipeline de enriquecimiento

- Extracción básica por plataforma.
- Clasificación (`lead_type`) en `utils/classifiers.py`.
- Señales de interés (`interest_signals`) en `utils/classifiers.py`.
- Scoring 0-100 en `utils/scoring.py`.
- Deduplicación/merge por `profile_url`, `social_handle`, `email` en `utils/dedupe.py`.
- Exportación CSV/JSON con `utils/exporters.py`.

## Consideraciones éticas y operativas

- Respeta TOS de cada plataforma.
- Reduce frecuencia si detectas throttling.
- Mantén scraping conservador (el proyecto ya limita scroll y resultados).
- Evita capturar datos sensibles no necesarios para prospección legítima.
