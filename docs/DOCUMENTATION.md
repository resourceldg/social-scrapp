# Social Scrapp — Documentación Técnica Completa

> Scraper multi-plataforma de leads sociales con scoring inteligente, anti-ban adaptativo y dashboard Streamlit para el nicho de arte contemporáneo, diseño de interiores y hospitalidad de lujo.

---

## Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Flujo de Datos Completo](#3-flujo-de-datos-completo)
4. [Instalación y Configuración](#4-instalación-y-configuración)
5. [Cómo Ejecutar](#5-cómo-ejecutar)
6. [Módulos del Sistema](#6-módulos-del-sistema)
   - 6.1 [config.py — Configuración Central](#61-configpy--configuración-central)
   - 6.2 [models/ — Modelo de Datos](#62-models--modelo-de-datos)
   - 6.3 [scrapers/ — Scrapers por Plataforma](#63-scrapers--scrapers-por-plataforma)
   - 6.4 [utils/browser.py — Driver de Chrome](#64-utilsbrowserpy--driver-de-chrome)
   - 6.5 [utils/database.py — Persistencia SQLite](#65-utilsdatabasepy--persistencia-sqlite)
   - 6.6 [utils/helpers.py — Extracción y Utilidades](#66-utilshelperspy--extracción-y-utilidades)
   - 6.7 [utils/dedupe.py y exporters.py](#67-utilsdedupy-y-exporterspy)
   - 6.8 [utils/profile_enricher.py — Enriquecimiento](#68-utilsprofile_enricherpy--enriquecimiento)
   - 6.9 [utils/keyword_ranker.py — UCB1 Ranking](#69-utilskeyword_rankerpy--ucb1-ranking)
   - 6.10 [utils/scoring.py y utils/classifiers.py](#610-utilsscoringpy-y-utilsclassifierspy)
   - 6.11 [core/ — Sistemas de Control Inteligentes](#611-core--sistemas-de-control-inteligentes)
   - 6.12 [scoring/ — Motor de Scoring Multi-Capa](#612-scoring--motor-de-scoring-multi-capa)
     - 6.12.1 [Business Intelligence Scoring](#6121-business-intelligence-scoring)
     - 6.12.2 [BuyingPowerScore — Capacidad de Compra](#6122-buyingpowerscore--capacidad-de-compra)
     - 6.12.3 [SpecifierScore — Poder de Decisión](#6123-specifierscore--poder-de-decisión)
     - 6.12.4 [ProjectSignalScore — Momento Adecuado](#6124-projectsignalscore--momento-adecuado)
     - 6.12.5 [Por qué los tres juntos](#6125-por-qué-los-tres-juntos)
   - 6.13 [signal_pipeline/ — Extracción de Señales](#613-signal_pipeline--extracción-de-señales)
   - 6.14 [opportunity_engine/ — Motor de Oportunidades](#614-opportunity_engine--motor-de-oportunidades)
   - 6.15 [feedback/ — Feedback Loop](#615-feedback--feedback-loop)
   - 6.16 [parsers/lead_parser.py](#616-parserslead_parserpy)
7. [Sistema Anti-Ban](#7-sistema-anti-ban)
8. [Base de Datos — Schema](#8-base-de-datos--schema)
9. [Dashboard Streamlit](#9-dashboard-streamlit)
10. [Automatización con Cron](#10-automatización-con-cron)
11. [Referencia de Variables de Entorno (.env)](#11-referencia-de-variables-de-entorno-env)
12. [Dependencias](#12-dependencias)
13. [Estructura de Directorios](#13-estructura-de-directorios)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Visión General

**Propósito**: Recopilar leads de alta calidad en seis redes sociales (Instagram, Facebook, LinkedIn, Pinterest, Reddit, Twitter/X) para prospectar compradores potenciales de arte contemporáneo, diseñadores de interiores, arquitectos, curadores y directivos de hospitality.

**Plataformas scrapeadas**: Instagram, Facebook, LinkedIn, Pinterest, Reddit, Twitter/X

**Salidas**:
- Base de datos SQLite con historial completo de leads
- CSV y JSON exportables
- Dashboard web interactivo (Streamlit)
- Logs de sesión rotados en `logs/`

**Flujo principal**:
```
run_scrape.sh → main.py (scrape) → enrich.py (visita perfiles) → dashboard.py (UI)
```

---

## 2. Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            PUNTO DE ENTRADA                             │
│   run_scrape.sh (cron/manual)                                           │
│   main.py (scrape) │ enrich.py (enriquecimiento) │ dashboard.py (UI)   │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
              ┌───────────────▼──────────────────────────┐
              │              FASE DE CONTROL              │
              │  NetworkProfiler → velocidad de conexión  │
              │  AdaptiveScheduler → plan de plataformas  │
              │  CircuitBreaker × 6 → aislamiento errores │
              │  RouteEvaluator → historial de rutas HTTP │
              └───────────────┬──────────────────────────┘
                              │
              ┌───────────────▼──────────────────────────┐
              │              SCRAPERS (× 6)               │
              │  InstagramScraper  │  FacebookScraper      │
              │  LinkedInScraper   │  PinterestScraper     │
              │  RedditScraper     │  TwitterScraper       │
              │                                           │
              │  Cada scraper:                            │
              │  → build_driver() con perfil Chrome       │
              │  → scroll_page()                          │
              │  → BeautifulSoup parse                    │
              │  → list[Lead]                             │
              └───────────────┬──────────────────────────┘
                              │
              ┌───────────────▼──────────────────────────┐
              │           PROCESAMIENTO                    │
              │  classifiers → lead_type + signals        │
              │  dedupe_leads() → merge duplicados        │
              │  ScoreEngine → score 0–100                │
              └───────────────┬──────────────────────────┘
                              │
              ┌───────────────▼──────────────────────────┐
              │             PERSISTENCIA                   │
              │  export_leads() → CSV + JSON              │
              │  upsert_leads() → SQLite                  │
              │  update_keyword_stats() → UCB1 data       │
              └───────────────┬──────────────────────────┘
                              │
              ┌───────────────▼──────────────────────────┐
              │          ENRIQUECIMIENTO (enrich.py)       │
              │  ProfileEnricher → visita perfil URL      │
              │  Extrae bio, followers, email, teléfono   │
              │  Ollama LLM (opcional) → re-clasifica     │
              └───────────────┬──────────────────────────┘
                              │
              ┌───────────────▼──────────────────────────┐
              │          DASHBOARD (Streamlit)             │
              │  Oportunidades │ Análisis │ Feedback       │
              │  Sistema │ Programación │ Configuración   │
              └─────────────────────────────────────────┘
```

---

## 3. Flujo de Datos Completo

### Fase 1 — Network Profiling
`NetworkProfiler.probe_initial_speed()` hace una petición HTTP a google.com y clasifica la conexión:
- **FAST**: < 800 ms
- **MEDIUM**: 800–2500 ms
- **SLOW**: > 2500 ms

Esto determina cuántos scrolls, plataformas y retries usar en la sesión.

### Fase 2 — Construcción del Plan
`AdaptiveScheduler.build_plan(scrapers)` genera una lista de `PlatformTask` con:
- Plataformas activas (filtradas por `{platform}_enabled`)
- Circuit breakers en estado OPEN excluidos
- `max_profiles`, `max_keywords`, `scrolls_per_page`, `retry_base_delay` ajustados por velocidad de red
- Orden por prioridad: LinkedIn → Reddit → Pinterest → Twitter → Facebook → Instagram

### Fase 3 — Loop de Scraping
Por cada plataforma activa:
1. **Verificar CircuitBreaker** → saltar si OPEN
2. **Ranking UCB1** → ordenar keywords por rendimiento histórico
3. **Cooldown filter** → excluir URLs vistas en los últimos N días
4. **Scrape con retry** → navegar, scrollear, parsear HTML → `list[Lead]`
5. **Actualizar métricas** → CircuitBreaker, RouteEvaluator, keyword_stats
6. **Cooldown split** → separar leads frescos de los ya vistos (touch_seen_profiles)

### Fase 4 — Procesamiento y Persistencia
- `enrich_lead()` → asigna `lead_type`, `interest_signals`, `score`
- `dedupe_leads()` → fusiona por URL + handle + email
- `export_leads()` → `output/leads.csv` y `output/leads.json`
- `upsert_leads()` → inserta/actualiza en SQLite

### Fase 5 — Enriquecimiento (enrich.py)
- Carga leads con score ≥ min_score que no fueron enriquecidos
- Visita cada `profile_url` en Selenium
- Extrae: bio completa, followers, email, teléfono, website
- Actualiza `enriched_at` en la base de datos

### Fase 6 — Dashboard
Streamlit lee de SQLite y permite ver, filtrar, marcar feedback y gestionar la automatización.

---

## 4. Instalación y Configuración

### Requisitos
- Python 3.11+
- Google Chrome instalado
- (Opcional) Ollama para clasificación LLM

### Instalación
```bash
# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Configuración inicial
```bash
# Copiar template de configuración
cp .env.example .env

# Editar con tus credenciales y paths
nano .env
```

Variables mínimas a configurar:
```dotenv
USER_DATA_DIR=/home/TU_USUARIO/.config/google-chrome
CHROME_PROFILE_PATH=Default
HEADLESS=true
```

### Configurar sesiones de redes sociales
Para scrapers que requieren login (Facebook, LinkedIn, Instagram):
1. Abrir Chrome con tu perfil real
2. Hacer login manualmente en cada plataforma
3. El scraper clonará las cookies automáticamente

Para Facebook con 2FA:
1. Abrir Chrome en `USER_DATA_DIR/CHROME_PROFILE_PATH`
2. Ir a facebook.com y completar 2FA
3. Una vez logueado la sesión persiste en las cookies clonadas

---

## 5. Cómo Ejecutar

### Ejecución completa (scrape + enriquecimiento)
```bash
./run_scrape.sh
```

### Solo scraping
```bash
./run_scrape.sh --scrape-only
# o directamente:
.venv/bin/python main.py
```

### Solo enriquecimiento
```bash
./run_scrape.sh --enrich-only --enrich-max 50 --enrich-min-score 3
# o directamente:
.venv/bin/python enrich.py --max 50 --min-score 3
```

### Dashboard web
```bash
.venv/bin/streamlit run dashboard.py
# Abre http://localhost:8501
```

### Ejecución paralela (un Chrome por plataforma)
```bash
.venv/bin/python parallel_runner.py
```

---

## 6. Módulos del Sistema

### 6.1 config.py — Configuración Central

Carga la configuración desde `.env` y la expone como un dataclass inmutable.

**Clase**: `AppConfig` (dataclass con slots)

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `chrome_profile_path` | str | `""` | Nombre del perfil Chrome (ej. "Default") |
| `user_data_dir` | str | `""` | Path al directorio de datos de Chrome |
| `headless` | bool | `False` | Ejecutar Chrome sin ventana |
| `max_profiles_per_platform` | int | 50 | Máximo de leads por plataforma por run |
| `max_results_per_query` | int | 20 | Máximo por keyword |
| `min_delay` / `max_delay` | float | 2.0 / 6.0 | Rango de delay aleatorio (segundos) |
| `output_dir` | Path | `output/` | Directorio para CSV/JSON |
| `sqlite_db_path` | Path | `output/leads.db` | Base de datos SQLite |
| `rescrape_cooldown_days` | int | 7 | No re-scraper un perfil en N días |
| `scrolls_override` | int | 4 | Profundidad de scroll (AdaptiveScheduler lo ajusta) |
| `{platform}_enabled` | bool | True | Toggle por plataforma |
| `{platform}_keywords` | List[str] | DEFAULT_KEYWORDS | Keywords a buscar |
| `{platform}_username/password` | str | `""` | Credenciales para auto-login |

**Función principal**: `load_config() → AppConfig`
- Llama a `load_dotenv(override=True)`
- Parsea booleanos con `_parse_bool()`, listas CSV con `_parse_csv()`
- Crea directorios necesarios (`output/`, `debug_html/`)

---

### 6.2 models/ — Modelo de Datos

**Clase**: `Lead` (dataclass frozen con slots) definida en `models/lead.py`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `source_platform` | str | instagram, facebook, linkedin, etc. |
| `search_term` | str | Keyword que generó este lead |
| `social_handle` | str | @handle o nombre de usuario |
| `profile_url` | str | URL canónica del perfil |
| `name` | str | Nombre visible del perfil |
| `email` / `phone` / `website` | str | Datos de contacto extraídos |
| `bio` | str | Texto de descripción (hasta 500 chars) |
| `city` / `country` | str | Ubicación detectada |
| `category` | str | Clasificación estructural (facebook_page, subreddit, etc.) |
| `lead_type` | str | Tipo de negocio (galeria, arquitecto, interiorista, etc.) |
| `interest_signals` | list[str] | Lista de señales detectadas |
| `followers` | int | Conteo de seguidores |
| `engagement_hint` | str | Indicador de engagement si está disponible |
| `score` | int | Score final 0–100 |
| `raw_data` | dict | Datos crudos específicos de la plataforma |

**Método**: `to_dict() → dict` para serialización a CSV/JSON.

---

### 6.3 scrapers/ — Scrapers por Plataforma

Todos los scrapers comparten la interfaz:
```python
def scrape(self, driver: WebDriver, config: AppConfig) -> list[Lead]
```

#### InstagramScraper
- **URL de búsqueda**: `/explore/tags/{hashtag}/` (dos candidatos: sanitizado + raw encoded)
- **Detección de bloqueo**: login wall, lite redirect, < 15 links
- **Sesión**: Persiste cookies en `output/instagram_session.json` (validas 25 días)
- **Login automático**: Intenta login con credenciales si la sesión falla
- **Paths excluidos**: `/p/`, `/reel/`, `/stories/`, `/tv/`, `/explore/`, `/accounts/`, `/direct/`

#### FacebookScraper
- **Estrategia headless-first**:
  1. Intenta con el driver headless del sistema principal
  2. Si el warm-up falla → `_run_with_visible(config)`
  3. Si el primer keyword devuelve `None` (bot-block) → `_run_with_visible(config)`
  4. `_run_with_visible()` construye su propio driver no-headless, scrappea todo, y lo cierra (no leaks)
- **URL de búsqueda**: `/search/top/?q={keyword}` (`/search/pages/` está deprecado)
- **Detección de sesión**: URL signals (`/login`, `/checkpoint`) + HTML markers (`id="email"`, `action="/login/device-based"`)
- **Login automático**: Rellena formulario con credenciales si está disponible
- **`_try_keyword()`**: Devuelve `None` si bot-block (< 500 bytes), `[]` si login wall, `list[Lead]` si OK
- **Normalización URLs**: `_normalize_fb_href()` elimina redirects `l.facebook.com`, tokens `pfbid*`, IDs numéricos largos, slugs de 1 char
- **Paths excluidos**: login, signup, events, marketplace, watch, reels, photos, videos, stories, groups/feed, ads, etc.

#### LinkedInScraper
- **URL de búsqueda**: `/search/results/all/?keywords={keyword}`
- **Detección login wall**: "authwall", "join now", "/login?", "sign in to linkedin"
- **Requiere**: Perfil Chrome con sesión LinkedIn activa
- **Normalización**: `_normalize_li_url()` elimina query params

#### PinterestScraper
- **URL de búsqueda**: `/search/users/?q={keyword}`
- **Regex de handle**: `/([a-zA-Z0-9_.-]{3,50})/`
- **Paths excluidos**: /pin/, /search/, /explore/, /ideas/, /today/, /login/

#### RedditScraper
- **URL de búsqueda**: `/search/?q={keyword}&type=sr,user`
- **Tipos**: Subreddits (`/r/*`) + perfiles de usuario (`/user/*`)
- **Formato canónico**: Primeros 2 segmentos del path (`/r/interiordesign`)

#### TwitterScraper (x.com)
- **URL de búsqueda**: `/search?q={keyword}&src=typed_query&f=user`
- **Regex de handle**: `[a-zA-Z0-9_]{1,50}`
- **Paths excluidos**: /search, /explore, /notifications, /messages, /home, /settings, /i/, /hashtag/
- **Handles garbage**: tos, privacy, about, help, rules, safety, jobs, ads, business, developers

---

### 6.4 utils/browser.py — Driver de Chrome

**Función**: `build_driver(config: AppConfig) → tuple[WebDriver, str | None]`

Devuelve el driver y el path del directorio temporal (debe limpiarse después de `driver.quit()`).

**Características**:
- **Anti-detección**: CDP script que elimina `navigator.webdriver`, simula plugins y lenguas
- **User-Agent rotatorio**: 5 variantes de Chrome (Windows, Mac, Linux)
- **Bloqueo de trackers**: Google Analytics, Facebook Pixel, Hotjar, Segment via CDP
- **Bloqueo de assets**: fuentes (.woff, .ttf), videos (.mp4, .webm) si `block_images=true`
- **Clonación de perfil**: Copia selectiva de archivos de sesión Chrome:
  - Archivos: Cookies, Login Data, Login Data For Account, Web Data, Preferences, Secure Preferences
  - Directorios: Network/
  - Archivo raíz: Local State
  - Esto evita el conflicto de singleton lock cuando Chrome ya está abierto
- **Opciones de estabilidad**: `--no-sandbox`, `--disable-dev-shm-usage`, `--window-size=1440,900`
- **Caché de disco**: 100 MB para acelerar recargas

**Función interna**: `_clone_profile(src_user_data, src_profile) → (tmp_dir, profile_name)`

---

### 6.5 utils/database.py — Persistencia SQLite

**Inicialización**: `init_db(db_path)` — crea el schema si no existe.

**Funciones principales**:

| Función | Descripción |
|---------|-------------|
| `start_run(db_path, notes)` | Inserta registro de run, devuelve `run_id` |
| `finish_run(db_path, run_id, status, raw, deduped)` | Actualiza run con resultados |
| `upsert_leads(db_path, leads, run_id)` | INSERT OR REPLACE con merge de datos |
| `get_unenriched_leads(db_path, min_score, max_leads)` | Para lote de enriquecimiento |
| `update_enriched_lead(db_path, url, updates)` | Actualiza campos enriquecidos |
| `mark_leads_enriched(db_path, urls)` | Setea `enriched_at = now()` |
| `get_recent_profile_urls(db_path, platform, days)` | URLs en cooldown window |
| `touch_seen_profiles(db_path, urls)` | Actualiza `last_seen_at` |
| `update_keyword_stats(db_path, platform, kw, leads)` | Acumula stats para UCB1 |
| `get_keyword_stats_df(db_path, platform)` | Pandas DF para ranking |
| `get_keyword_stats_df(db_path)` | All platforms |

---

### 6.6 utils/helpers.py — Extracción y Utilidades

**Extracción de datos de texto**:
- `extract_emails(text)` — regex de email estándar
- `extract_phones(text)` — regex de teléfono internacional
- `extract_website(text)` — URL regex + filtro de dominios sociales
- `extract_follower_count(text)` — detecta "12.5K", "1,234", "500+", "2M"
- `detect_location(text) → (city, country)` — diccionario de ciudades/países prioritarios

**Interacción con página**:
- `scroll_page(driver, scrolls, min_delay, max_delay)` — scroll adaptativo: espera hasta que la altura del DOM cambie
- `save_debug_html(driver, dir, filename, enabled)` — guarda snapshot HTML para debugging

**Control de flujo**:
- `scrape_with_retry(fn, max_retries, base_delay, label) → T` — backoff exponencial, solo reintenta en excepciones

**URLs**:
- `normalize_url(url)` — elimina query params y fragmentos para deduplicación
- `check_url_reachable(url)` — HEAD request con timeout

---

### 6.7 utils/dedupe.py y exporters.py

**`dedupe_leads(leads: list[Lead]) → list[Lead]`**:
- Claves de merge: URL normalizada + social_handle + email
- Lógica de fusión: union de `interest_signals`, merge de `raw_data`, preferencia por campos no vacíos
- Resultado: Leads únicos con datos maximizados

**`export_leads(leads, output_dir)`**:
- `output/leads.csv` — via Pandas
- `output/leads.json` — JSON con soporte unicode

---

### 6.8 utils/profile_enricher.py — Enriquecimiento

**Clase**: `ProfileEnricher(min_score, max_leads, inter_delay)`

**Método**: `enrich_batch(driver, leads, config, on_progress) → list[Lead]`

**Proceso por lead**:
1. Navegar a `profile_url`
2. Extraer meta tags (`og:description`, etc.)
3. Parsear HTML: email, teléfono, website, followers, bio completa
4. Re-clasificar con LLM (Ollama) si está disponible
5. Actualizar `lead_type`, `interest_signals`, `score`

**Caso especial Reddit**: Usa la API pública JSON de Reddit (`/r/{subreddit}/about.json` o `/user/{name}/about.json`) en vez de Selenium — más rápido y sin bot detection.

---

### 6.9 utils/keyword_ranker.py — UCB1 Ranking

Implementa el algoritmo **Upper Confidence Bound (UCB1)** para bandit multi-armed: balance entre explorar keywords nuevos y explotar los que ya demostran funcionar.

**Fórmula**:
```
UCB = avg_score + C × √(ln(total_runs + 1) / (run_count + 1))
```

**Constantes**:
- `UCB_C = 2.0` — coeficiente de exploración
- `MIN_RUNS = 3` — mínimo de runs antes de podar
- `PRUNE_BELOW = 3.0` — avg_score mínimo para seguir intentando
- Keywords desconocidos: score `inf` → siempre se intentan primero

**Funciones**:
- `rank_keywords(db_path, platform, keywords) → list[str]` — ordena por UCB score
- `summarise_keyword_performance(db_path, platform) → str` — tabla de rendimiento

---

### 6.10 utils/scoring.py y utils/classifiers.py

**`score_lead(lead) → int`**: Entry point backward-compatible. Delega a `ScoreEngine(mode=OUTREACH_PRIORITY).score(lead).final_score`

**`classify_lead(text) → str`**: Detecta tipo de lead por patrones de texto.

**Lead types**: `coleccionista`, `arquitecto`, `interiorista`, `galeria`, `curador`, `diseñador`, `estudio`, `hospitality`, `hotel`, `restaurante`, `tienda decoracion`, `artista`, `maker`, `marca premium`, `desarrollador`

**`extract_interest_signals(text) → list[str]`**: Extrae señales de interés.

**Signals**: arte contemporáneo, curaduría, arquitectura, decoración, gallery, exhibition, handcrafted, bespoke, luxury, collectors, etc.

---

### 6.11 core/ — Sistemas de Control Inteligentes

#### CircuitBreaker (`core/circuit_breaker.py`)

Patrón circuit breaker por plataforma para aislar fallos:

```
CLOSED ──(4 fallos consecutivos)──▶ OPEN
  ▲                                   │
  │                             (300 segundos)
  │                                   │
  └──(2 éxitos en HALF_OPEN)── HALF_OPEN ◀─┘
```

| Estado | Comportamiento |
|--------|---------------|
| CLOSED | Normal, permite requests |
| OPEN | Plataforma salteada completamente |
| HALF_OPEN | Permite 1 probe request |

**Config**: `failure_threshold=4`, `success_threshold=2`, `open_timeout_s=300`

#### NetworkProfiler (`core/network_profiler.py`)

- **Probe inicial**: HTTP a `google.com/generate_204` → clasifica FAST/MEDIUM/SLOW
- **Monitoreo continuo**: `record_page_load(elapsed_ms, timed_out)` durante el scraping
- **Umbrales**:
  - Probe: 800ms=MEDIUM, 2500ms=SLOW
  - Page loads: 4000ms=MEDIUM, 9000ms=SLOW
  - Timeout rate: >30%=SLOW, >12%=MEDIUM

**Estrategias por velocidad**:
| Velocidad | max_scrolls | max_plataformas | retry_delay |
|-----------|-------------|-----------------|-------------|
| FAST | 4 | 6 | 4s |
| MEDIUM | 3 | 4 | 6s |
| SLOW | 2 | 2 | 10s |

#### RouteEvaluator (`core/route_evaluator.py`)

Aprende qué rutas URL funcionan bien y penaliza las que fallan.

**Scoring**:
```
stability_score = success_rate × confidence_factor
confidence_factor → 1.0 a partir de 20+ muestras
rutas desconocidas: score = 0.65 (neutro)
rutas penalizadas: score < 0.25 (después de 6+ muestras con alta tasa de fallo)
```

#### AdaptiveScheduler (`core/scheduler.py`)

`build_plan(scrapers) → list[PlatformTask]`

Genera un plan adaptado por sesión:
1. Filtra plataformas habilitadas + circuit breakers no OPEN
2. Ordena por prioridad por defecto (LinkedIn primero, Instagram último)
3. Escala `max_profiles`, `max_keywords`, `scrolls_per_page` según velocidad de red

#### MetricsCollector (`core/metrics.py`)

Acumula por plataforma: leads encontrados, keywords intentados, timeouts, retries, circuit breaks.

**Output**: `output/metrics_{timestamp}.json`

---

### 6.12 scoring/ — Motor de Scoring Multi-Capa

**Clase**: `ScoreEngine(mode: RankingMode)`
**Método**: `score(lead: Lead) → LeadScoreResult`

#### Pipeline de scoring

```
Lead
  │
  ▼
SignalExtractor.extract() → SignalSet
  │
  ▼
7 Dimensiones (0–100 c/u):
  ├─ Contactability  (email/phone presente)
  ├─ Relevance       (match con keywords/bio/categoría)
  ├─ Authority       (followers, engagement)
  ├─ Commercial Intent (señales de compra)
  ├─ Premium Fit     (marcadores de lujo y exclusividad)
  ├─ Platform Specific (factores nativos de cada plataforma)
  └─ Data Quality    (completitud de campos)
  │
  ▼
Suma ponderada por RankingMode → base_score
  │
  ▼
Business Scoring (0–100 c/u):
  ├─ BuyingPower (poder adquisitivo estimado)
  ├─ Specifier   (autoridad de decisión: arquitecto, curador, etc.)
  └─ ProjectSignal (proyecto activo/inminente)
  │
  ▼
OpportunityScore (suma ponderada de componentes de negocio)
  │
  ▼
LeadScoreResult:
  final_score (0–100), dimensions{}, business_scores{},
  classifications, reasons[], confidence
```

#### Modos de Ranking (`scoring/weights_config.py`)

| Modo | Uso recomendado |
|------|-----------------|
| `OUTREACH_PRIORITY` (default) | Contactabilidad + relevancia |
| `AUTHORITY_FIRST` | Influencers, colaboraciones de marca |
| `PREMIUM_FIT_FIRST` | Compradores de alta gama |
| `CONTACTABILITY_FIRST` | Leads calientes con datos de contacto |
| `SPECIFIER_NETWORK` | Arquitectos/diseñadores con poder de decisión |
| `HOT_PROJECT_DETECTION` | Proyectos activos/inminentes |

**Pesos por defecto (OUTREACH_PRIORITY)**:
```
contactability=0.22, relevance=0.20, commercial_intent=0.18,
authority=0.14, premium_fit=0.12, platform_specific=0.10, data_quality=0.04
```

---

### 6.12.1 Business Intelligence Scoring

El sistema va más allá de un scoring técnico (relevancia, autoridad, contactabilidad) para responder preguntas de negocio reales. Los tres scores de inteligencia comercial miden dimensiones distintas y complementarias de oportunidad:

| Score | Pregunta | Archivo |
| ----- | -------- | ------- |
| **BuyingPowerScore** | ¿Puede pagar? | `scoring/business_scoring/buying_power.py` |
| **SpecifierScore** | ¿Puede decidir qué se compra? | `scoring/business_scoring/specifier.py` |
| **ProjectSignalScore** | ¿Hay un proyecto activo ahora? | `scoring/business_scoring/project_signal.py` |

La fórmula final de oportunidad los combina con el score base:

```
OpportunityScore =
    BaseLeadScore      × 0.40
  + BuyingPowerScore   × 0.20
  + SpecifierScore     × 0.20
  + ProjectSignalScore × 0.20
```

Los pesos varían por `RankingMode`. Por ejemplo, `HOT_PROJECT_DETECTION` eleva `ProjectSignalScore` al 35%.

---

### 6.12.2 BuyingPowerScore — Capacidad de Compra

**Qué mide**: La probabilidad de que el lead tenga presupuesto —o acceso a presupuesto— para comprar arte, diseño de colección u objetos de lujo.

No mide riqueza personal necesariamente, sino capacidad económica dentro de un contexto profesional o comercial. Un interior designer que trabaja para hoteles de lujo maneja presupuestos grandes aunque no sea el dueño.

**Señales utilizadas**:

| Categoría | Ejemplos |
| --------- | -------- |
| Ciudades / mercados premium | Miami, Madrid, Barcelona, Punta del Este, Dubai, London |
| Perfil de cliente | `private clients`, `luxury residential`, `high-end interiors`, `premium developments` |
| Tipo de proyecto | `boutique hotel`, `residential tower`, `private residence`, `hospitality design` |
| Madurez profesional | `design studio`, `architecture firm`, `creative director`, `principal architect`, `founder` |

**Fórmula conceptual**:

```
BuyingPowerScore =
    market_tier          × 0.30
  + project_type_value   × 0.30
  + client_profile_value × 0.25
  + professional_maturity × 0.15
```

---

### 6.12.3 SpecifierScore — Poder de Decisión

**Qué mide**: La probabilidad de que el lead decida qué se compra, aunque no sea quien paga.

En arquitectura, interiorismo y arte esto es crítico: quien paga no siempre decide. La cadena de decisión típica en un hotel es:

```
hotel owner → architect → interior designer → art consultant → artworks / objects
```

El que elige el arte suele ser el interior designer o el art consultant, no el dueño.

**Señales utilizadas**:

| Categoría | Ejemplos |
| --------- | -------- |
| Títulos profesionales | `architect`, `interior designer`, `curator`, `art consultant`, `design director`, `procurement` |
| Lenguaje de selección | `curating spaces`, `material selection`, `art curation`, `design sourcing`, `commissioned work`, `site specific art` |
| Tipo de proyecto | `hospitality project`, `residential project`, `interior architecture`, `concept design` |
| Autoridad profesional | `principal`, `head of design`, `creative lead`, LinkedIn amplifica +20% |

**Fórmula conceptual**:

```
SpecifierScore =
    role_strength        × 0.40
  + project_involvement  × 0.30
  + selection_language   × 0.20
  + professional_authority × 0.10
```

---

### 6.12.4 ProjectSignalScore — Momento Adecuado

**Qué mide**: La probabilidad de que exista un proyecto activo en este momento.

Este score introduce el factor tiempo: un lead puede ser perfecto en perfil pero sin proyecto actual. El timing lo cambia todo.

**Señales utilizadas**:

| Categoría | Ejemplos |
| --------- | -------- |
| Lenguaje de proyecto | `new project`, `opening soon`, `under construction`, `renovation`, `installation`, `fit-out`, `launching` |
| Señales temporales (recency_hint=True) | `next month`, `coming soon`, `currently working on`, `excited to unveil` |
| Actividad visible | `site visit`, `progress update`, `installation week`, `project reveal` |

**Recency multiplier**: Las señales con `recency_hint=True` elevan el `ProjectSignalScore` hasta 1.5× (implementado en `signal_pipeline/signal_types.py` via `SignalSet.recency_score`).

**Fórmula conceptual**:

```
ProjectSignalScore =
    recency              × 0.35
  + explicit_project_terms × 0.35
  + construction_signals × 0.20
  + activity_density     × 0.10
```

---

### 6.12.5 Por qué los tres juntos

Los tres scores se complementan cubriendo dimensiones independientes. Un score alto en uno no implica alto en los otros:

| Caso | BuyingPower | Specifier | ProjectSignal | Interpretación |
| ---- | ----------- | --------- | ------------- | -------------- |
| Arquitecto con proyecto activo | 60 | 85 | 80 | Prescriptor fuerte con proyecto → lead muy valioso |
| Developer inmobiliario | 90 | 40 | 60 | Alto poder de compra pero decisión delegada |
| Influencer de diseño | 30 | 20 | 10 | No compra ni prescribe, pero AuthorityScore alto → colaboración de marca |
| Collector privado | 85 | 75 | 15 | Comprador y decisor, pero sin proyecto activo hoy |

La combinación de los tres convierte el sistema de un scraper de perfiles en un **opportunity detection system**: no solo encuentra personas, sino momentos de compra dentro de un ecosistema.

---

### 6.13 signal_pipeline/ — Extracción de Señales

**Enum**: `SignalType` — ROLE, INDUSTRY, LUXURY, PROJECT, MARKET

**Clase**: `Signal(signal_type, value, source, weight=1.0, recency_hint=bool)`

**Clase**: `SignalSet` — agrega las 5 listas de señales
- Propiedades: `density`, `weighted_density`, `active_types`, `has_project_signals`, `recency_score`

**`SignalExtractor.extract(lead) → SignalSet`** orquesta 5 extractores:
- `role_extractor` — Architect, designer, curator, collector, gallery owner
- `industry_extractor` — Contemporary art, hospitality, real estate, furniture, jewelry
- `luxury_extractor` — Premium, bespoke, exclusive, limited edition
- `project_extractor` — Keywords de proyectos activos (renovación, nuevo hotel, brief de diseño)
- `market_extractor` — Señales geográficas, foco en Latinoamérica

---

### 6.14 opportunity_engine/ — Motor de Oportunidades

**`compute_opportunity_score(base, buying_power, specifier, project, mode) → (int, reasons)`**
- Suma ponderada de 4 componentes según `OPPORTUNITY_WEIGHTS[mode]`

**`classify_lead(lead, signal_set) → str`**
- Lead types: gallery, art_consultant, architect, interior_designer, hospitality, collector, developer, design_studio, brand, artist

**`classify_opportunity(lead, signal_set) → str`**
- Opportunity types: specifier_network, active_project, buyer, influencer, partner

---

### 6.15 feedback/ — Feedback Loop

#### FeedbackStore (`feedback/feedback_store.py`)
```python
store = FeedbackStore(db_path)
store.mark_outcome(profile_url, "converted")    # cliente ganado
store.mark_outcome(profile_url, "disqualified") # descartado
```

#### FeedbackAnalyzer (`feedback/feedback_analyzer.py`)
- Compara señales de leads convertidos vs descartados
- Sugiere calibraciones del scoring
- Reporte de efectividad por plataforma y tipo de lead

---

### 6.16 parsers/lead_parser.py

`soup_from_html(html: str) → BeautifulSoup`

Todos los scrapers usan esta función para parsear HTML con `html.parser`.

---

## 7. Sistema Anti-Ban

El sistema implementa 11 capas de protección contra detección y bloqueo:

| Capa | Mecanismo | Dónde |
|------|-----------|-------|
| 1 | **Network profiling**: adapta velocidad según conexión | NetworkProfiler |
| 2 | **Circuit breakers**: skip plataformas tras 4 fallos | CircuitBreaker |
| 3 | **Route evaluation**: evita rutas URL penalizadas | RouteEvaluator |
| 4 | **Keyword UCB1**: prioriza keywords históricam. buenos | keyword_ranker |
| 5 | **Cooldown filter**: no re-scrappear perfil en 7 días | database |
| 6 | **Clonación de sesión**: hereda cookies Chrome sin conflicto | browser._clone_profile |
| 7 | **Stealth JS**: elimina `navigator.webdriver`, simula plugins | CDP injection |
| 8 | **User-Agent rotation**: 5 variantes de Chrome real | browser |
| 9 | **Delays aleatorios**: variación temporal entre acciones | scroll_page, delays |
| 10 | **Límites de recursos**: max_profiles, scrolls, keywords por sesión | AppConfig |
| 11 | **Facebook headless-first**: intenta headless, cae a visible solo si bot-block | FacebookScraper |

### Estrategia específica de Facebook
```
1. Warm-up en driver headless
   ├─ OK → intentar keywords en headless
   │    ├─ Primer keyword OK → continuar headless
   │    └─ Primer keyword bot-block (< 500 bytes) → _run_with_visible()
   └─ Fallo → _run_with_visible()

_run_with_visible():
   ├─ build_driver(headless=False)  ← su propio driver
   ├─ warm-up + login si necesario
   ├─ scrape todos los keywords
   └─ driver.quit() + cleanup tmp_dir  ← en finally block
```

---

## 8. Base de Datos — Schema

Archivo: `output/leads.db` (SQLite)

### Tabla: scraping_runs
```sql
id           INTEGER PRIMARY KEY
started_at   DATETIME DEFAULT CURRENT_TIMESTAMP
finished_at  DATETIME
status       TEXT  -- 'running' | 'completed' | 'failed'
total_raw_leads    INTEGER DEFAULT 0
total_deduped_leads INTEGER DEFAULT 0
notes        TEXT
```

### Tabla: leads
```sql
id              INTEGER PRIMARY KEY
run_id          INTEGER REFERENCES scraping_runs(id)
source_platform TEXT
search_term     TEXT
name            TEXT
social_handle   TEXT
profile_url     TEXT UNIQUE
email           TEXT
phone           TEXT
website         TEXT
city            TEXT
country         TEXT
bio             TEXT
category        TEXT
lead_type       TEXT
interest_signals TEXT  -- JSON array
followers       INTEGER
engagement_hint TEXT
score           INTEGER DEFAULT 0
raw_data        TEXT  -- JSON object
scrape_count    INTEGER DEFAULT 1
last_seen_at    DATETIME
created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
status          TEXT DEFAULT 'new'
enriched_at     DATETIME
```

### Tabla: conversions
```sql
id          INTEGER PRIMARY KEY
profile_url TEXT UNIQUE
outcome     TEXT  -- 'converted' | 'disqualified'
marked_at   DATETIME DEFAULT CURRENT_TIMESTAMP
notes       TEXT
```

### Tabla: keyword_stats
```sql
id           INTEGER PRIMARY KEY
platform     TEXT
keyword      TEXT
run_count    INTEGER DEFAULT 0
total_leads  INTEGER DEFAULT 0
high_leads   INTEGER DEFAULT 0  -- score >= HIGH_THRESHOLD
warm_leads   INTEGER DEFAULT 0  -- score >= WARM_THRESHOLD
avg_score    REAL DEFAULT 0.0
last_run_at  DATETIME
UNIQUE(platform, keyword)
```

### Tabla: route_stats
```sql
pattern       TEXT
platform      TEXT
success_count INTEGER DEFAULT 0
failure_count INTEGER DEFAULT 0
last_success_at DATETIME
last_failure_at DATETIME
updated_at    DATETIME
PRIMARY KEY(pattern, platform)
```

---

## 9. Dashboard Streamlit

**Ejecutar**: `streamlit run dashboard.py` → http://localhost:8501

### Tabs

| Tab | Contenido |
|-----|-----------|
| **🎯 Oportunidades** | Tabla de leads con filtros (plataforma, tipo, score mínimo, búsqueda de texto), botones de feedback (convertido/descartado) |
| **📊 Análisis** | Gráficos Plotly: distribución por plataforma, histograma de scores, embudo de conversión, evolución temporal |
| **🔄 Feedback** | Leads marcados como convertidos/descartados, recomendaciones del FeedbackAnalyzer |
| **📡 Sistema** | Estado de circuit breakers, estabilidad de rutas, métricas de la última sesión (JSON) |
| **⏰ Programación** | Editor de crontab, botón de inicio/parada del scraper, estado del lock file |
| **⚙️ Configuración** | Editor del `.env` (plataformas, keywords, credenciales), viewer de logs recientes |

**Funciones internas**:
- `_get_scrape_status()` — verifica `.scrape.lock`
- `_kill_scrape(pid)` — SIGTERM al proceso
- `_parse_scraper_crons()` — lee/edita crontab del usuario

---

## 10. Automatización con Cron

El script `run_scrape.sh` gestiona la ejecución segura:

**Features**:
- Lock file (`/.scrape.lock`) previene ejecuciones solapadas
- `nice -n 10 ionice -c 3` — prioridad baja de CPU y disco
- Rotación de logs (últimos 10 archivos en `logs/`)
- Exporta `DISPLAY=:0` y `WAYLAND_DISPLAY=wayland-0` para Chrome no-headless en cron
- Cleanup automático (SIGINT/SIGTERM)

**Agregar al crontab** (`crontab -e`):

```cron
# Opción A — Semanal (mínimo riesgo de ban)
0 3 * * 0  cd /home/zen/Documents/social-scrapp && ./run_scrape.sh

# Opción B — Dos veces por semana
0 3 * * 0,3  cd /home/zen/Documents/social-scrapp && ./run_scrape.sh

# Opción C — Scrape domingo, enriquecimiento miércoles
0 3 * * 0    cd /home/zen/Documents/social-scrapp && ./run_scrape.sh --scrape-only
0 3 * * 3    cd /home/zen/Documents/social-scrapp && ./run_scrape.sh --enrich-only
```

---

## 11. Referencia de Variables de Entorno (.env)

```dotenv
# ── Browser ───────────────────────────────────────────────────────────────
CHROME_PROFILE_PATH=Default         # nombre del perfil Chrome
USER_DATA_DIR=/home/user/.config/google-chrome  # directorio de datos Chrome
HEADLESS=true                       # true/false
PAGE_LOAD_TIMEOUT=60                # segundos de espera Selenium
NETWORK_RETRIES=3                   # reintentos por keyword

# ── Límites de Scraping ───────────────────────────────────────────────────
MAX_PROFILES_PER_PLATFORM=25        # leads máximos por plataforma
MAX_RESULTS_PER_QUERY=15            # por keyword
MAX_SEARCHES_PER_SESSION=5          # keywords máximos por run
MIN_DELAY=3.5                       # delay mínimo entre acciones (segundos)
MAX_DELAY=9.0                       # delay máximo
RESCRAPE_COOLDOWN_DAYS=7            # días antes de re-scrappear un perfil

# ── Storage ───────────────────────────────────────────────────────────────
OUTPUT_DIR=output
SAVE_DEBUG_HTML=false               # true guarda snapshots HTML en debug_html/
SQLITE_DB_PATH=output/leads.db
BLOCK_IMAGES=true                   # bloquea descarga de imágenes

# ── Plataformas ───────────────────────────────────────────────────────────
INSTAGRAM_ENABLED=true
FACEBOOK_ENABLED=true
LINKEDIN_ENABLED=true
PINTEREST_ENABLED=true
REDDIT_ENABLED=true
TWITTER_ENABLED=true

# ── Keywords (CSV separado por comas) ─────────────────────────────────────
INSTAGRAM_KEYWORDS=#artecontemporaneo,#galeriadearteBA,#collectibledesign
FACEBOOK_KEYWORDS=galerías de arte,estudios de arquitectura,interiorismo
LINKEDIN_KEYWORDS=galería de arte director,art advisor argentina
PINTEREST_KEYWORDS=collectible design,luxury interior art,art collector home
REDDIT_KEYWORDS=interior design,contemporary art,art collecting
TWITTER_KEYWORDS=art collector interior,galería de arte directora

# ── Credenciales ─────────────────────────────────────────────────────────
INSTAGRAM_USERNAME=
INSTAGRAM_PASSWORD=
FACEBOOK_USERNAME=
FACEBOOK_PASSWORD=
LINKEDIN_USERNAME=
LINKEDIN_PASSWORD=
TWITTER_USERNAME=
TWITTER_PASSWORD=
PINTEREST_USERNAME=
PINTEREST_PASSWORD=
REDDIT_USERNAME=
REDDIT_PASSWORD=
```

---

## 12. Dependencias

```
selenium              # WebDriver (Chrome automation)
beautifulsoup4        # HTML parsing
pandas                # Data analysis + CSV export
plotly                # Interactive charts
streamlit             # Web UI
webdriver-manager     # ChromeDriver auto-download/update
python-dotenv         # .env loading
requests              # HTTP requests (enrichment, reachability checks)
```

Para instalar:
```bash
pip install -r requirements.txt
```

---

## 13. Estructura de Directorios

```
social-scrapp/
│
├── main.py                  # Entry point principal (scrape completo)
├── enrich.py                # Entry point de enriquecimiento
├── dashboard.py             # Dashboard Streamlit
├── parallel_runner.py       # Scraping multi-proceso
├── config.py                # Configuración central
├── run_scrape.sh            # Wrapper bash para cron
├── .env                     # Variables de entorno (no commitear)
│
├── models/
│   ├── __init__.py
│   └── lead.py              # Dataclass Lead
│
├── scrapers/
│   ├── __init__.py
│   ├── instagram_scraper.py
│   ├── facebook_scraper.py
│   ├── linkedin_scraper.py
│   ├── pinterest_scraper.py
│   ├── reddit_scraper.py
│   └── twitter_scraper.py
│
├── parsers/
│   ├── __init__.py
│   └── lead_parser.py       # soup_from_html()
│
├── utils/
│   ├── browser.py           # build_driver(), _clone_profile()
│   ├── database.py          # SQLite CRUD completo
│   ├── helpers.py           # Extracción de datos, scroll, retry
│   ├── classifiers.py       # classify_lead(), extract_interest_signals()
│   ├── dedupe.py            # dedupe_leads()
│   ├── exporters.py         # export_leads() → CSV + JSON
│   ├── profile_enricher.py  # ProfileEnricher.enrich_batch()
│   ├── keyword_ranker.py    # UCB1 ranking
│   ├── scoring.py           # score_lead() entry point
│   ├── logging_setup.py     # Configuración de logging
│   ├── contact_enricher.py  # Enriquecimiento de contacto multi-fuente
│   └── llm_classifier.py    # Clasificación con Ollama
│
├── core/
│   ├── circuit_breaker.py   # CircuitBreaker por plataforma
│   ├── network_profiler.py  # NetworkProfiler (FAST/MEDIUM/SLOW)
│   ├── route_evaluator.py   # RouteEvaluator (historial rutas)
│   ├── scheduler.py         # AdaptiveScheduler
│   └── metrics.py           # MetricsCollector
│
├── scoring/
│   ├── score_engine.py      # ScoreEngine (pipeline completo)
│   ├── base_scoring.py      # 7 dimensiones de scoring
│   ├── weights_config.py    # RankingMode + pesos
│   ├── ab_test.py           # A/B testing de modos
│   ├── business_scoring/
│   │   ├── buying_power.py
│   │   ├── specifier.py
│   │   └── project_signal.py
│   └── platform_scoring/
│       └── (per-platform scorers)
│
├── signal_pipeline/
│   ├── signal_types.py      # SignalType, Signal, SignalSet
│   ├── signal_extractor.py  # SignalExtractor
│   └── extractors/
│       ├── role_extractor.py
│       ├── industry_extractor.py
│       ├── luxury_extractor.py
│       ├── project_extractor.py
│       └── market_extractor.py
│
├── opportunity_engine/
│   ├── opportunity_scorer.py
│   └── opportunity_classifier.py
│
├── feedback/
│   ├── feedback_store.py    # FeedbackStore (mark_outcome)
│   └── feedback_analyzer.py # Análisis de conversiones
│
├── output/                  # Generado automáticamente
│   ├── leads.db
│   ├── leads.csv
│   ├── leads.json
│   └── metrics_*.json
│
├── logs/                    # Session logs (últimos 10)
│   └── session_YYYYMMDD_HHMMSS.log
│
└── debug_html/              # HTML snapshots (si SAVE_DEBUG_HTML=true)
    └── facebook_{keyword}.html
```

---

## 14. Troubleshooting

### Facebook devuelve 0 leads
1. Verificar que estás logueado en Chrome (`USER_DATA_DIR/CHROME_PROFILE_PATH`)
2. Abrir Chrome manualmente en facebook.com y confirmar sesión activa
3. Si pidió 2FA, completarla manualmente antes de correr el scraper
4. Activar `SAVE_DEBUG_HTML=true` y revisar `debug_html/facebook_*.html`
5. Verificar logs: si dice "warm-up ok" pero 0 leads, el scraper encontró la sesión pero no results en la búsqueda

### Chrome no inicia (error de perfil)
- Error "user data directory is already in use": Chrome está abierto usando el mismo perfil
- El scraper clona el perfil automáticamente para evitar esto — pero si hay un error en la clonación puede fallar
- Solución: Cerrar Chrome antes de correr el scraper (la clonación funciona con Chrome abierto normalmente)

### LinkedIn/Instagram no encuentra resultados
- Verificar que hay sesión activa en Chrome para esa plataforma
- Activar `SAVE_DEBUG_HTML=true` para ver qué HTML devuelve
- Puede haber un login wall: revisar logs para "login wall detected"

### Error de ChromeDriver version mismatch
```bash
# webdriver-manager lo actualiza automáticamente normalmente
# Si falla manualmente:
pip install --upgrade webdriver-manager
```

### Cron no ejecuta (Chrome no abre)
- Verificar que `DISPLAY=:0` está seteado (el script lo hace automáticamente)
- Para debug: `DISPLAY=:0 ./run_scrape.sh --scrape-only`
- Revisar logs en `logs/session_*.log`

### Score siempre en 0
- Ejecutar `enrich.py` para completar el scoring
- El scoring básico se aplica en `main.py` pero el full score requiere enriquecimiento

### Base de datos bloqueada
```bash
# Si el scraper terminó mal y el lock file quedó:
rm .scrape.lock
# Para SQLite corruption (raro):
sqlite3 output/leads.db ".recover" | sqlite3 output/leads_recovered.db
```
