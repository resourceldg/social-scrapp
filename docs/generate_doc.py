"""
Generate layered architecture documentation as PDF.
Run: python docs/generate_doc.py
Output: docs/social-scrapp-architecture.pdf
"""
from __future__ import annotations
from pathlib import Path
from fpdf import FPDF

OUT = Path(__file__).parent / "social-scrapp-architecture.pdf"

# ── Colour palette ──────────────────────────────────────────────────────────
C_BLACK   = (20,  20,  20)
C_WHITE   = (255, 255, 255)
C_DARK    = (40,  40,  40)
C_GREY    = (100, 100, 100)
C_LGREY   = (230, 230, 230)
C_XLGREY  = (245, 245, 245)

# Layer accent colours
LAYER_COLORS = {
    1: (41,  128, 185),   # blue  — Ingesta
    2: (39,  174,  96),   # green — Scoring
    3: (142,  68, 173),   # purple — IA / LLM
    4: (231,  76,  60),   # red   — Almacenamiento
    5: (243, 156,  18),   # orange — Dashboard
    6: (22,  160, 133),   # teal  — Automatización
}


FONT_DIR = "/usr/share/fonts/truetype"
SANS         = f"{FONT_DIR}/dejavu/DejaVuSans.ttf"
SANS_BOLD    = f"{FONT_DIR}/dejavu/DejaVuSans-Bold.ttf"
SANS_ITALIC  = f"{FONT_DIR}/dejavu/DejaVuSans-Oblique.ttf"
MONO         = f"{FONT_DIR}/liberation/LiberationMono-Regular.ttf"


class Doc(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        self.add_font("Sans",  "",  SANS)
        self.add_font("Sans",  "B", SANS_BOLD)
        self.add_font("Sans",  "I", SANS_ITALIC)
        self.add_font("Mono",  "",  MONO)
        self.set_auto_page_break(auto=True, margin=18)
        self.add_page()

    # ── Helpers ─────────────────────────────────────────────────────────────

    def rgb(self, color: tuple):
        return color

    def set_fill(self, color):
        self.set_fill_color(*color)

    def set_draw(self, color):
        self.set_draw_color(*color)

    def set_text(self, color):
        self.set_text_color(*color)

    # ── Cover ────────────────────────────────────────────────────────────────

    def cover(self):
        self.set_fill(C_DARK)
        self.rect(0, 0, 210, 297, "F")

        self.set_text(C_WHITE)
        self.set_font("Sans", "B", 28)
        self.set_y(70)
        self.cell(0, 12, "Social Scrapper", align="C", new_x="LMARGIN", new_y="NEXT")

        self.set_font("Sans", "", 15)
        self.set_text((180, 180, 180))
        self.cell(0, 8, "Arquitectura por capas — Documentación técnica", align="C", new_x="LMARGIN", new_y="NEXT")

        self.ln(10)
        self.set_draw((80, 80, 80))
        self.set_line_width(0.4)
        self.line(30, self.get_y(), 180, self.get_y())
        self.ln(10)

        # Layer index on cover
        self.set_font("Sans", "", 11)
        layers = [
            (1, "Capa 1 · Ingesta y scraping"),
            (2, "Capa 2 · Scoring determinístico"),
            (3, "Capa 3 · Inteligencia artificial"),
            (4, "Capa 4 · Almacenamiento y deduplicación"),
            (5, "Capa 5 · Dashboard y exportación"),
            (6, "Capa 6 · Automatización y ciclo de feedback"),
        ]
        for num, label in layers:
            col = LAYER_COLORS[num]
            self.set_fill(col)
            self.set_text(C_WHITE)
            self.set_x(30)
            self.cell(150, 9, f"  {label}", fill=True, new_x="LMARGIN", new_y="NEXT")
            self.ln(1)

        self.ln(20)
        self.set_text((120, 120, 120))
        self.set_font("Sans", "I", 9)
        self.cell(0, 6, "Marzo 2026", align="C")

    # ── Section header ────────────────────────────────────────────────────────

    def section(self, layer_num: int, title: str, subtitle: str = ""):
        self.add_page()
        col = LAYER_COLORS[layer_num]
        self.set_fill(col)
        self.rect(0, 0, 210, 28, "F")
        self.set_text(C_WHITE)
        self.set_font("Sans", "B", 16)
        self.set_y(7)
        self.cell(0, 8, title, align="C", new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            self.set_font("Sans", "", 10)
            self.set_text((220, 220, 220))
            self.cell(0, 5, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_y(34)
        self.set_text(C_DARK)

    # ── Subsection ────────────────────────────────────────────────────────────

    def h2(self, text: str, layer_num: int = 0):
        self.ln(3)
        if layer_num:
            col = LAYER_COLORS[layer_num]
            self.set_fill(col)
        else:
            self.set_fill(C_LGREY)
        self.set_text(C_WHITE if layer_num else C_DARK)
        self.set_font("Sans", "B", 11)
        self.cell(0, 7, f"  {text}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text(C_DARK)
        self.ln(2)

    # ── Body text ─────────────────────────────────────────────────────────────

    def body(self, text: str):
        self.set_font("Sans", "", 10)
        self.set_text(C_DARK)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    # ── Code block ────────────────────────────────────────────────────────────

    def code(self, text: str, label: str = ""):
        if label:
            self.set_font("Sans", "I", 8)
            self.set_text(C_GREY)
            self.cell(0, 5, label, new_x="LMARGIN", new_y="NEXT")
        self.set_fill(C_XLGREY)
        self.set_draw(C_LGREY)
        self.set_text((50, 50, 150))
        self.set_font("Mono", "", 8)
        self.set_line_width(0.2)
        lines = text.strip().split("\n")
        padding = 3
        self.set_x(self.l_margin)
        total_h = len(lines) * 4.5 + padding * 2
        x, y = self.get_x(), self.get_y()
        self.rect(x, y, 190, total_h, "DF")
        self.set_y(y + padding)
        for line in lines:
            self.set_x(self.l_margin + 3)
            self.cell(0, 4.5, line, new_x="LMARGIN", new_y="NEXT")
        self.set_y(y + total_h + 2)
        self.set_text(C_DARK)
        self.set_draw(C_DARK)

    # ── Table ─────────────────────────────────────────────────────────────────

    def table(self, headers: list[str], rows: list[list[str]], col_widths: list[float] | None = None):
        if col_widths is None:
            w = 190 / len(headers)
            col_widths = [w] * len(headers)

        # Header
        self.set_fill(C_DARK)
        self.set_text(C_WHITE)
        self.set_font("Sans", "B", 9)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, f"  {h}", fill=True, border=0)
        self.ln()

        # Rows
        self.set_font("Sans", "", 9)
        for ri, row in enumerate(rows):
            self.set_fill(C_XLGREY if ri % 2 == 0 else C_WHITE)
            self.set_text(C_DARK)
            for i, cell in enumerate(row):
                self.cell(col_widths[i], 6.5, f"  {cell}", fill=True, border=0)
            self.ln()
        self.ln(2)

    # ── Bullet list ──────────────────────────────────────────────────────────

    def bullets(self, items: list[str], indent: int = 5):
        self.set_font("Sans", "", 10)
        self.set_text(C_DARK)
        for item in items:
            self.set_x(self.l_margin + indent)
            self.cell(4, 5.5, "•")
            self.multi_cell(0, 5.5, item)
        self.ln(1)

    # ── Divider ──────────────────────────────────────────────────────────────

    def divider(self, color: tuple = C_LGREY):
        self.ln(2)
        self.set_draw(color)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), 210 - self.r_margin, self.get_y())
        self.ln(4)


# ── Build document ──────────────────────────────────────────────────────────

doc = Doc()
doc.cover()


# ════════════════════════════════════════════════════════════════════════════
# CAPA 1 — Ingesta y scraping
# ════════════════════════════════════════════════════════════════════════════
doc.section(1, "Capa 1 · Ingesta y scraping",
            "Recolección de perfiles desde redes sociales")

doc.h2("Propósito")
doc.body(
    "Esta capa es responsable de conectar con cada plataforma (Instagram, LinkedIn, Pinterest, "
    "Reddit, Twitter/X, Facebook), buscar perfiles mediante keywords configurables, y devolver "
    "objetos Lead sin procesar. Opera a través de un driver Selenium con perfil Chrome clonado "
    "para heredar la sesión autenticada del usuario."
)

doc.h2("Archivos principales")
doc.table(
    ["Archivo", "Responsabilidad"],
    [
        ["scrapers/instagram_scraper.py", "Búsqueda por hashtag, detección de login, login programático JS"],
        ["scrapers/linkedin_scraper.py",  "Búsqueda por query, extracción de slug (con filtro de sufijos)"],
        ["scrapers/twitter_scraper.py",   "Búsqueda de handles, filtro de cuentas basura (tos, privacy…)"],
        ["scrapers/pinterest_scraper.py", "Búsqueda por keyword de diseño/coleccionismo"],
        ["scrapers/reddit_scraper.py",    "Subreddits y usuarios vía API JSON pública"],
        ["utils/browser.py",              "Construcción del driver con anti-fingerprint y clonado de perfil"],
    ],
    col_widths=[90, 100]
)

doc.h2("Flujo de ingesta")
doc.code("""\
config.instagram_keywords (desde .env)
    ↓  rank_keywords()  →  UCB-ranked list
    ↓  cap a task.max_keywords  (anti-ban)
    ↓  scraper.scrape(driver, config)
    ↓  cooldown filter (profile_url reciente → skip)
    ↓  List[Lead]  →  Capa 2 (scoring)""")

doc.h2("Anti-detección")
doc.bullets([
    "CDP stealth: navigator.webdriver = undefined, plugins falsos, chrome.runtime inyectado",
    "User-agent rotado aleatoriamente entre 5 cadenas realistas",
    "Bloqueo de trackers (Google Analytics, Meta Pixel, Hotjar…) vía Network.setBlockedURLs",
    "Clonado del perfil Chrome: copia solo Cookies, Login Data, Network/ — evita conflicto de lock",
    "--password-store=gnome-libsecret para descifrar cookies v11 GNOME Keyring",
    "Login programático Instagram: JS value + dispatchEvent (React), JS click (bypass interceptors)",
])

doc.h2("Configuración relevante (.env)")
doc.code("""\
INSTAGRAM_KEYWORDS='#collectibledesign, #coleccionismoarte, …'
LINKEDIN_KEYWORDS='art advisor argentina, luxury interior designer, …'
MAX_SEARCHES_PER_SESSION=5
MIN_DELAY=3.5 / MAX_DELAY=9.0   # delay aleatorio entre requests
RESCRAPE_COOLDOWN_DAYS=7         # cooldown por profile_url""")


# ════════════════════════════════════════════════════════════════════════════
# CAPA 2 — Scoring determinístico
# ════════════════════════════════════════════════════════════════════════════
doc.section(2, "Capa 2 · Scoring determinístico",
            "Puntuación basada en reglas — fuente de verdad inalterable")

doc.h2("Propósito")
doc.body(
    "Asigna una puntuación numérica (0–100+) a cada lead basándose exclusivamente en señales "
    "objetivas extraídas del perfil. Este scoring es la fuente de verdad del sistema y NO se "
    "modifica por las capas de IA — en cambio, las capas superiores enriquecen los campos que "
    "este scoring lee (bio, engagement_hint, lead_type), mejorando indirectamente el resultado."
)

doc.h2("Motor de scoring — scoring/score_engine.py")
doc.body("Fórmula compuesta:")
doc.code("""\
score = base_score × w_base + buying_power × w_bp + semantic_relevance × w_sem

base_score      →  señales de rol, seguidores, contactabilidad
buying_power    →  señales de compra/especificación detectadas en bio + engagement_hint
semantic_relevance →  similitud con embeddings de leads ideales (sentence-transformers)""")

doc.h2("Niveles de score")
doc.table(
    ["Rango", "Nivel", "Significado", "Acción sugerida"],
    [
        ["≥ 70",  "HIGH",  "Comprador directo o especificador activo",   "Outreach inmediato"],
        ["40–69", "WARM",  "Profesional relacionado, influye en compras", "Nutrir + seguimiento"],
        ["10–39", "COLD",  "Sector relacionado, sin señal clara",         "Monitorear"],
        ["0–9",   "NOISE", "Sin relación con el nicho",                   "Descartar"],
    ],
    col_widths=[22, 22, 90, 56]
)

doc.h2("Señales de buying_power detectadas")
doc.bullets([
    "Menciones de 'coleccionista', 'colección', 'curador' en bio o categoría",
    "Términos de compra activa: 'acquisition', 'commission', 'galería privada'",
    "Cargo: art advisor, gallery director, interior designer, hospitality director",
    "engagement_hint con intent:X/10 inyectado por el clasificador LLM (Capa 3)",
    "Presencia de email/website → bonus de contactabilidad",
])

doc.h2("Semantic relevance — scoring/semantic_relevance.py")
doc.body(
    "Usa sentence-transformers (all-MiniLM-L6-v2, 22 MB, CPU) para calcular similitud coseno "
    "entre el texto del lead y un conjunto de ejemplos de leads ideales. Activa automáticamente "
    "si el paquete está instalado; si no, el componente retorna 0 sin romper el pipeline."
)


# ════════════════════════════════════════════════════════════════════════════
# CAPA 3 — Inteligencia artificial
# ════════════════════════════════════════════════════════════════════════════
doc.section(3, "Capa 3 · Inteligencia artificial",
            "LLM local + UCB keyword ranker — sin fine-tuning, sin dependencia de nube")

doc.h2("Principio de diseño")
doc.body(
    "La IA opera en dos instancias independientes: (A) clasificación de bio en tiempo de "
    "enriquecimiento usando un LLM local, y (B) optimización de keywords entre runs mediante "
    "un algoritmo UCB. Ninguna capa de IA modifica el scoring determinístico directamente — "
    "enriquecen los campos que el scoring lee."
)

doc.h2("A · Clasificador LLM de bio — utils/llm_classifier.py")
doc.body("Modelo: qwen2.5:1.5b via Ollama (local, ~1 GB RAM, CPU-only, ~2 s/lead)")
doc.code("""\
Input:  bio text (max 600 chars)
Output: {
  "buying_intent": 0–10,
  "lead_type":     "collector | interior_designer | gallery_director | …",
  "reason":        "< 15 palabras"
}

Criterios de buying_intent:
  8–10  →  comprador directo / especificador activo
  5–7   →  profesional que influye en compras
  2–4   →  sector relacionado, sin señal clara
  0–1   →  sin relación""")

doc.body(
    "El resultado se almacena en engagement_hint ('intent:8/10 — coleccionista activo de arte "
    "contemporáneo') y en lead_type. El scoring de Capa 2 lee ambos campos, elevando el score "
    "final de perfiles que el scraper hubiera dejado pasar."
)
doc.body("Fallback silencioso: si Ollama no está corriendo, se omite sin bloquear el pipeline.")

doc.h2("B · UCB Keyword Ranker — utils/keyword_ranker.py")
doc.body(
    "Después de cada run, agrega estadísticas de calidad por keyword y plataforma en "
    "keyword_stats (SQLite). Antes del siguiente run, ordena los keywords usando la fórmula UCB1:"
)
doc.code("""\
ucb(kw) = avg_score
         + high_bonus  (high_leads × 1.5)
         + C × sqrt( ln(total_runs + 1) / (run_count + 1) )

C = 2.0  →  balance exploración / explotación
high_leads = leads con score ≥ 8  (compradores directos)""")

doc.h2("Niveles de clasificación de keywords")
doc.table(
    ["Estado", "Criterio", "Comportamiento"],
    [
        ["Nuevo",           "0 runs",                          "UCB = ∞ → siempre corre primero"],
        ["Activo",          "run_count ≥ 1, avg_score ≥ 3",   "Ordenado por UCB normal"],
        ["Baja prioridad",  "run_count ≥ 3, avg_score < 3, high=0", "Al final de la lista, sigue corriendo"],
    ],
    col_widths=[38, 80, 72]
)

doc.body(
    "No existe eliminación automática de keywords — un keyword 'muerto' puede recuperarse si "
    "la red social cambia su audiencia. La decisión de borrar es siempre humana."
)

doc.h2("Por qué no fine-tuning")
doc.bullets([
    "Los datos serán escasos los primeros meses → overfitting garantizado con < 200 ejemplos",
    "Few-shot dinámico (ejemplos reales inyectados en el prompt) da mejor resultado sin costo",
    "El LLM base qwen2.5:1.5b ya tiene conocimiento de roles del sector arte/diseño/lujo",
    "Cuando el DB supere ~500 leads confirmados, se puede considerar fine-tuning con LoRA",
])


# ════════════════════════════════════════════════════════════════════════════
# CAPA 4 — Almacenamiento y deduplicación
# ════════════════════════════════════════════════════════════════════════════
doc.section(4, "Capa 4 · Almacenamiento y deduplicación",
            "SQLite persistente + lógica upsert robusta")

doc.h2("Tablas SQLite — output/leads.db")
doc.table(
    ["Tabla", "Descripción", "Clave única"],
    [
        ["leads",          "Leads enriquecidos y puntuados",               "profile_url / (social_handle, platform)"],
        ["scraping_runs",  "Historial de ejecuciones con totales",         "id autoincrement"],
        ["conversions",    "Feedback de conversión (outcome por URL)",     "profile_url"],
        ["keyword_stats",  "Rendimiento acumulado por keyword/plataforma", "(platform, keyword)"],
    ],
    col_widths=[38, 100, 52]
)

doc.h2("Lógica de upsert — utils/database.py · upsert_leads()")
doc.body(
    "Cada lead se intenta insertar con ON CONFLICT(profile_url) DO UPDATE. Si falla por "
    "UNIQUE(social_handle, platform) (e.g. LinkedIn extrae 'en' como handle), hace fallback "
    "a UPDATE por handle+platform. Si ambos fallan, loguea y continúa — nunca crashea la sesión."
)
doc.code("""\
try:
    conn.execute(INSERT ... ON CONFLICT(profile_url) DO UPDATE ...)
except sqlite3.IntegrityError:
    try:
        conn.execute(UPDATE ... WHERE social_handle=? AND source_platform=?)
    except Exception as exc:
        logger.warning("Skipping lead: %s", exc)""")

doc.h2("Campos clave del modelo Lead")
doc.table(
    ["Campo", "Fuente", "Uso en scoring"],
    [
        ["bio",             "og:description / scraper",     "buying_power, semantic_relevance"],
        ["lead_type",       "classify_lead() / LLM",        "base_score (rol)"],
        ["engagement_hint", "LLM → 'intent:X/10 — …'",     "buying_power"],
        ["score",           "score_engine.py",              "filtro enriquecimiento, dashboard"],
        ["search_term",     "keyword que encontró el lead", "keyword_stats (UCB feedback)"],
        ["enriched_at",     "enrich.py",                    "evita re-enriquecer innecesariamente"],
    ],
    col_widths=[40, 70, 80]
)

doc.h2("Deduplicación — utils/dedupe.py")
doc.body(
    "Antes de persistir, elimina duplicados dentro del mismo batch por profile_url normalizado "
    "(lowercase, trailing slash removido). Los duplicados cross-run se manejan con upsert "
    "actualizando score y scrape_count."
)


# ════════════════════════════════════════════════════════════════════════════
# CAPA 5 — Dashboard y exportación
# ════════════════════════════════════════════════════════════════════════════
doc.section(5, "Capa 5 · Dashboard y exportación",
            "Streamlit · visualización, gestión de leads y exportación CRM")

doc.h2("Tabs del dashboard")
doc.table(
    ["Tab", "Contenido"],
    [
        ["Oportunidades",  "Tabla principal con filtros, modal de detalle, modo de vista, exportación CSV"],
        ["Analisis",       "KPIs, calidad por plataforma, distribución de scores, rendimiento de keywords UCB"],
        ["Feedback",       "Registro de conversiones (outcome: ganado/perdido/en-proceso)"],
        ["Sistema",         "Estado de Ollama, sentence-transformers, base de datos"],
        ["Programacion",   "Editor de cron, logs en vivo, ejecución manual de scraping/enriquecimiento"],
        ["Config",         "Editor de .env con validación, recarga en caliente"],
    ],
    col_widths=[45, 145]
)

doc.h2("Modos de vista — Oportunidades")
doc.table(
    ["Modo", "Orden", "Uso"],
    [
        ["Score",           "score DESC",                    "Ver el universo completo rankeado"],
        ["Outreach",        "contactabilidad + relevancia",  "Cold outreach — tienen email o web"],
        ["Contactabilidad", "email/web primero",             "Acción inmediata hoy"],
        ["Nuevos",          "created_at DESC",               "Leads de las últimas 24h"],
    ],
    col_widths=[40, 70, 80]
)

doc.h2("Modal de detalle — fixes aplicados")
doc.bullets([
    "Reapertura en loop corregida: _leads_tbl_prev_sel rastrea la última fila seleccionada",
    "NaN/None/nan convertidos a '' por _safe_str() antes de renderizar",
    "Estado del lead se guarda explícitamente con botón 'Guardar' (no auto-save)",
])

doc.h2("Exportación")
doc.bullets([
    "CSV: todos los campos incluyendo engagement_hint (intent LLM visible)",
    "Botón en dashboard: descarga filtrada por la vista activa",
    "Formato compatible con HubSpot, Notion, Airtable, Salesforce",
])


# ════════════════════════════════════════════════════════════════════════════
# CAPA 6 — Automatización y ciclo de feedback
# ════════════════════════════════════════════════════════════════════════════
doc.section(6, "Capa 6 · Automatización y ciclo de feedback",
            "Cron · circuit breaker · keyword loop · few-shot futuro")

doc.h2("Pipeline completo por run")
doc.code("""\
[cron]  run_scrape.sh
  ├── python main.py
  │     1. Network probe (velocidad → ajusta scroll depth)
  │     2. AdaptiveScheduler → plan de plataformas + keyword cap
  │     3. Por plataforma:
  │           a. CircuitBreaker.allow_request()
  │           b. rank_keywords() → UCB order
  │           c. scraper.scrape()  →  List[Lead]
  │           d. cooldown filter
  │           e. update_keyword_stats()  ← feedback loop
  │     4. enrich_lead() (scoring inicial)
  │     5. dedupe → export → upsert
  │     6. summarise_keyword_performance() → log
  │
  └── python enrich.py  (si ENRICH=true en run_scrape.sh)
        1. get_unenriched_leads(min_score=3, limit=50)
        2. build_driver()
        3. ProfileEnricher.enrich_batch()
              ├── _enrich_instagram / linkedin / …
              ├── _re_enrich()
              │     ├── classify_lead() + extract_interest_signals()
              │     └── classify_bio()  ← Ollama LLM (si disponible)
              └── score_lead()  ← score final elevado""")

doc.h2("Circuit Breaker — core/circuit_breaker.py")
doc.bullets([
    "4 fallos consecutivos → plataforma en estado OPEN por 5 minutos",
    "Evita ban por requests repetidos cuando una plataforma está caída o bloqueando",
    "Se resetea automáticamente al primer éxito después del timeout",
])

doc.h2("Ciclo de feedback keyword (UCB) — resumen visual")
doc.code("""\
Run N:
  keywords → scrape → leads con scores
                   ↓
              update_keyword_stats(platform, kw, leads)
                   ↓  SQLite keyword_stats

Run N+1:
  rank_keywords() lee keyword_stats
       ↓
  ucb = avg_score + high_bonus + C×sqrt(ln(total+1)/(runs+1))
       ↓
  keywords ordenados: mejores primero, muertos al final
       ↓
  cap a max_keywords → scraper""")

doc.h2("Evolución futura — few-shot dinámico")
doc.body(
    "Cuando el DB supere ~50 leads con buying_intent ≥ 7 (confirmados por el LLM o manualmente), "
    "se puede activar few-shot dinámico en llm_classifier.py: antes de clasificar una nueva bio, "
    "se inyectan 3 ejemplos reales del mismo lead_type en el prompt. Esto mejora la precisión "
    "sin fine-tuning ni costos adicionales."
)
doc.code("""\
# Ejemplo de prompt con few-shot (futuro):
Ejemplos de 'interior_designer' con alta intención:
  Bio: "Directora de proyectos residenciales luxury en Buenos Aires…"  → intent: 9
  Bio: "Interiorista especializada en colecciones de arte…"            → intent: 8

Ahora clasifica:
  Bio: "{nueva_bio}"  →""")

doc.h2("Configuración del cron (run_scrape.sh)")
doc.code("""\
ENRICH=true
ENRICH_MAX=50
ENRICH_MIN_SCORE=3      # era 20 — cambiado para romper el chicken-and-egg

# Ejemplo crontab:
0 8 * * 1,3,5   cd ~/Documents/social-scrapp && bash run_scrape.sh
# Lunes, miércoles, viernes a las 8:00""")


# ── Save ────────────────────────────────────────────────────────────────────
Path(OUT).parent.mkdir(parents=True, exist_ok=True)
doc.output(str(OUT))
print(f"PDF generado: {OUT}")
