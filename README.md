# Lead Intelligence — Social Scraper

Sistema de detección y calificación de leads para el sector de **arte contemporáneo, diseño de colección, interiorismo y hospitalidad**. Scraping conservador, scoring multidimensional, dashboard analítico y ejecución automática programada.

---

## Características principales

| Capa | Qué hace |
|---|---|
| **Scraping adaptativo** | 6 plataformas (Instagram, LinkedIn, Twitter, Facebook, Pinterest, Reddit). Detecta velocidad de red y ajusta límites automáticamente. |
| **Anti-ban integrado** | CircuitBreaker por plataforma, cooldown de perfiles (14 días por defecto), keyword cap por sesión, delays aleatorios humanizados (3.5–9s). |
| **Score Engine** | 8 dimensiones × 7 modos de ranking → score 0–100 + oportunidad + clasificación. |
| **Enriquecimiento** | Visita perfiles top para extraer bio real, followers, email y website. |
| **Dashboard** | 6 pestañas: Oportunidades, Análisis, Feedback, Sistema, Programación, Configuración. |
| **Programación** | Cron configurable desde el dashboard. Run + kill desde UI. Log en vivo. |

---

## Estructura del proyecto

```
social-scrapp/
├── main.py                  # Entry point del scraping
├── enrich.py                # Entry point del enriquecimiento de perfiles
├── dashboard.py             # Dashboard Streamlit (6 tabs)
├── config.py                # Configuración centralizada desde .env
├── run_scrape.sh            # Runner seguro (nice, ionice, lock file, log rotation)
├── start_dashboard.sh       # Inicia el dashboard en background
├── .env                     # Variables de entorno (credenciales + config)
│
├── core/
│   ├── scheduler.py         # AdaptiveScheduler — plan de ejecución por sesión
│   ├── network_profiler.py  # NetworkProfiler — clasifica velocidad de red
│   ├── circuit_breaker.py   # CircuitBreaker — suspende plataformas con fallos
│   ├── route_evaluator.py   # RouteEvaluator — tracking de éxito por ruta
│   └── metrics.py           # MetricsCollector — métricas de sesión
│
├── scrapers/
│   ├── instagram_scraper.py
│   ├── linkedin_scraper.py
│   ├── twitter_scraper.py
│   ├── facebook_scraper.py
│   ├── pinterest_scraper.py
│   └── reddit_scraper.py
│
├── scoring/
│   ├── score_engine.py      # ScoreEngine — orquestador principal (8 pasos)
│   ├── score_result.py      # LeadScoreResult dataclass (18+ campos)
│   ├── base_scoring.py      # 7 dimensiones universales (0–100 c/u)
│   ├── business_scoring.py  # BuyingPower, Specifier, ProjectSignal
│   ├── weights_config.py    # 7 RankingModes + multiplicadores por plataforma
│   └── platform_scoring/    # Scorer específico por plataforma
│
├── signal_pipeline/
│   └── signal_extractor.py  # Extrae señales de nicho del bio/categoría
│
├── opportunity_engine/
│   ├── opportunity_scorer.py     # OpportunityScore (0–100)
│   └── opportunity_classifier.py # Clasifica tipo de oportunidad
│
├── feedback/
│   ├── feedback_store.py    # Guarda conversiones/descartados
│   └── feedback_analyzer.py # Análisis de calibración del scoring
│
├── models/
│   └── lead.py              # Lead dataclass
│
├── utils/
│   ├── database.py          # SQLite: upsert, cooldown, enriquecimiento
│   ├── browser.py           # Chrome builder (headless, perfil de usuario)
│   ├── scoring.py           # score_lead() — API pública simplificada
│   ├── profile_enricher.py  # Visita perfiles con Selenium
│   ├── contact_enricher.py  # Extrae email/web de páginas de contacto
│   ├── dedupe.py            # Deduplicación de leads por URL/handle/email
│   ├── classifiers.py       # Clasificación lead_type + interest_signals
│   └── exporters.py         # Exporta CSV/JSON
│
├── output/                  # Base de datos y exportaciones (generado en runtime)
│   ├── leads.db             # SQLite (leads + runs + conversions)
│   ├── leads.csv
│   └── leads.json
│
└── logs/                    # Logs de sesión (rotación automática, últimos 10)
    └── session_YYYYMMDD_HHMMSS.log
```

---

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con credenciales y keywords
```

---

## Configuración (.env)

### Parámetros de rendimiento local

| Variable | Valor recomendado | Descripción |
|---|---|---|
| `HEADLESS` | `true` | Sin ventana visible. Ahorra ~20% de RAM. |
| `MAX_PROFILES_PER_PLATFORM` | `25` | Perfiles por plataforma por sesión. |
| `MAX_RESULTS_PER_QUERY` | `15` | Resultados por keyword. |
| `MAX_SEARCHES_PER_SESSION` | `5` | Keywords procesadas por plataforma. |
| `RESCRAPE_COOLDOWN_DAYS` | `14` | Días antes de re-scrapear un perfil. |
| `MIN_DELAY` / `MAX_DELAY` | `3.5` / `9.0` | Delay entre acciones (simula comportamiento humano). |
| `BLOCK_IMAGES` | `true` | Ahorra ~80% de ancho de banda. |
| `SAVE_DEBUG_HTML` | `false` | Solo activar para depurar selectores rotos. |

### Consumo de recursos en PC local (16GB RAM)

| Componente | RAM |
|---|---|
| Chrome headless (scraping) | ~700 MB |
| Python main.py | ~150 MB |
| Python enrich.py | ~150 MB |
| Streamlit dashboard (idle) | ~200 MB |
| **Total durante scraping** | **~1.2 GB de 17 GB** |

---

## Ejecución

### Dashboard (mantener siempre activo)

```bash
./start_dashboard.sh          # inicia en background → http://localhost:8501
./start_dashboard.sh status   # ¿está corriendo?
./start_dashboard.sh stop     # parar
./start_dashboard.sh logs     # tail -f del log del dashboard
```

### Scraping manual

```bash
./run_scrape.sh               # scraping completo + enriquecimiento
./run_scrape.sh --scrape-only  # solo recolectar leads (sin visitar perfiles)
./run_scrape.sh --enrich-only  # solo enriquecer perfiles top (sin scraping nuevo)
```

`run_scrape.sh` incluye:
- **Lock file**: previene ejecuciones paralelas (Chrome es single-threaded aquí)
- **`nice -n 10`**: Chrome en prioridad CPU baja — el escritorio no se congela
- **`ionice -c 3`**: I/O en clase idle — el disco sigue disponible para el sistema
- **Log rotation**: guarda los últimos 10 logs en `logs/`

### Programación automática

Gestionada desde el dashboard en la pestaña **⏰ Programación**. También editable manualmente:

```bash
crontab -e
```

Calendario recomendado para este nicho:

```
# Scraping completo — Domingos a las 3:00 AM
0 3 * * 0  cd /ruta/social-scrapp && ./run_scrape.sh >> /dev/null 2>&1

# Solo enriquecimiento — Miércoles a las 3:00 AM
0 3 * * 3  cd /ruta/social-scrapp && ./run_scrape.sh --enrich-only >> /dev/null 2>&1
```

---

## Pipeline de scoring

```
Lead
 │
 ├─ 1. SignalExtractor       → señales de nicho (role/luxury/project/market)
 ├─ 2. Dimensiones base      → 7 scores universales (0–100 c/u)
 │      contactability · relevance · authority · commercial_intent
 │      premium_fit · data_quality · platform_specific
 ├─ 3. Multiplicadores       → ajuste por plataforma
 ├─ 4. RankingMode weights   → suma ponderada → final_score (0–100)
 ├─ 5. Business scoring      → buying_power · specifier · project_signal
 ├─ 6. OpportunityEngine     → opportunity_score + clasificación
 │      active_project · direct_buyer · specifier_network
 │      strategic_partner · low_signal
 ├─ 7. SpamRisk              → autenticidad 0–100
 └─ 8. LeadScoreResult       → 18+ campos + reasons + warnings + confidence
```

### 7 modos de ranking (seleccionables en el dashboard)

| Modo | Foco |
|---|---|
| `outreach_priority` | Equilibrio contactabilidad + relevancia + intención. Default. |
| `authority_first` | Alcance e influencia. Para colaboraciones de marca. |
| `premium_fit_first` | Coleccionistas y compradores premium. |
| `contactability_first` | Los más fáciles de contactar hoy (tienen email o web). |
| `brand_relevance` | Afinidad temática con arte/diseño/lujo. |
| `specifier_network` | Arquitectos, diseñadores, interioristas que prescriben compras. |
| `hot_project_detection` | Señales de proyecto activo o intención inmediata. |

---

## Dashboard — 6 pestañas

| Pestaña | Qué muestra |
|---|---|
| 🎯 **Oportunidades** | Tabla filtrable, análisis profundo por lead (8 dimensiones, razones, acción sugerida), exportaciones, ranking mode selector. |
| 📊 **Análisis** | KPIs generales, calidad por plataforma, distribución de scores, mapa geográfico, perfiles recurrentes, histórico de runs. |
| 🔄 **Feedback** | Registro de conversiones/descartados para calibración del modelo. |
| 📡 **Sistema** | Salud del scoring, distribución de spam risk, densidad de señales, lead types. |
| ⏰ **Programación** | Estado del proceso en tiempo real, kill/run desde UI, log en vivo, editor de cron. |
| ⚙️ **Configuración** | Todas las variables de `.env` editables sin tocar el archivo. |

---

## Exportaciones disponibles

| Perfil | Contenido | Uso |
|---|---|---|
| **Outreach** | Leads con email o web + score ≥ 60. Columnas en español. | CRM / contacto directo |
| **CRM** | Todos los campos limpios. | HubSpot, Notion, Airtable |
| **Investigación** | Con bio, señales y contexto. | Análisis manual |
| **Ejecutivo** | Top 20 con prioridad y tipo de contacto. | Presentación al equipo |
| **Completo (JSON)** | Todos los campos. | Análisis técnico |

---

## Anti-ban — capas activas

1. **CircuitBreaker**: Si una plataforma falla 4 veces, se suspende 5 minutos automáticamente.
2. **Cooldown filter**: Perfiles vistos en los últimos 14 días se omiten.
3. **Keyword cap**: Máximo 5 keywords por plataforma por sesión.
4. **AdaptiveScheduler**: En conexión lenta, reduce plataformas (máx 2) y scrolls.
5. **Delays humanizados**: Esperas aleatorias 3.5–9s entre acciones.
6. **Block images**: Reduce tráfico y tiempo de carga (~80% menos bandwidth).
7. **nice + ionice**: El proceso no compite con el SO por CPU ni disco.

---

## Depuración de selectores rotos

Cuando una plataforma cambia su DOM y el scraper deja de extraer datos:

```bash
# 1. Activar debug HTML temporalmente
# En .env: SAVE_DEBUG_HTML=true

# 2. Ejecutar solo esa plataforma (desde dashboard Configuración, desactivar el resto)
./run_scrape.sh --scrape-only

# 3. Inspeccionar el HTML generado
ls debug_html/

# 4. Ajustar selectores en scrapers/<plataforma>_scraper.py

# 5. Desactivar debug HTML
# En .env: SAVE_DEBUG_HTML=false
```

---

## Notas de uso ético

- Este proyecto extrae **únicamente información pública** o visible para la cuenta autenticada.
- No evade captchas, 2FA ni rate limits de plataformas.
- Diseñado para volúmenes bajos (25 perfiles / plataforma / semana) dentro del uso normal de un usuario humano.
- Las cuentas utilizadas deben ser tuyas y el uso debe cumplir los ToS de cada plataforma.
