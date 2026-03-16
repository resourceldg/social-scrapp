#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_scrape.sh — safe local scraping runner
#
# Features:
#   - Lock file prevents overlapping runs (Chrome is single-threaded here)
#   - nice + ionice: Chrome runs at lower priority so desktop stays responsive
#   - Log rotation: keeps last 10 sessions in logs/
#   - Scraping + enrichment are separate, sequential steps
#   - Graceful cleanup on Ctrl+C or kill
#
# Usage:
#   ./run_scrape.sh              # full run (scrape + enrich top 30)
#   ./run_scrape.sh --scrape-only
#   ./run_scrape.sh --enrich-only
#   ./run_scrape.sh --enrich-max 50 --enrich-min-score 25
#
# Schedule via cron (see SCHEDULING section at bottom of this file).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin/python"
LOCK="$SCRIPT_DIR/.scrape.lock"
LOG_DIR="$SCRIPT_DIR/logs"
MAX_LOGS=10          # keep last N session logs
ENRICH_MAX=50        # profiles to enrich per run
ENRICH_MIN_SCORE=3   # minimum score to bother enriching (all non-empty leads)

# ── Argument parsing ──────────────────────────────────────────────────────────
DO_SCRAPE=true
DO_ENRICH=true

for arg in "$@"; do
  case $arg in
    --scrape-only)   DO_ENRICH=false ;;
    --enrich-only)   DO_SCRAPE=false ;;
    --enrich-max=*)  ENRICH_MAX="${arg#*=}" ;;
    --enrich-min-score=*) ENRICH_MIN_SCORE="${arg#*=}" ;;
  esac
done

# ── Log setup ─────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/session_${TIMESTAMP}.log"

# Rotate: keep only the last MAX_LOGS files (|| true: no-op when no session logs exist yet)
ls -t "$LOG_DIR"/session_*.log 2>/dev/null | tail -n +$((MAX_LOGS + 1)) | xargs -r rm -- || true

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ── Lock file (prevent overlapping runs) ──────────────────────────────────────
if [ -f "$LOCK" ]; then
  LOCK_PID=$(cat "$LOCK" 2>/dev/null || echo "unknown")
  if kill -0 "$LOCK_PID" 2>/dev/null; then
    log "ABORT: another scraping session is running (PID $LOCK_PID). Exiting."
    exit 1
  else
    log "WARN: stale lock file found (PID $LOCK_PID no longer running). Removing."
    rm -f "$LOCK"
  fi
fi

echo $$ > "$LOCK"

cleanup() {
  log "Cleanup triggered — removing lock file."
  rm -f "$LOCK"
}
trap cleanup EXIT INT TERM

# ── Display (needed for FACEBOOK_HEADLESS=false in cron where $DISPLAY is unset)
# Cron strips the environment; export the user's X display so Chrome can open a window.
# Falls back to :0 (standard primary display on most single-user Linux desktops).
if [ -z "${DISPLAY:-}" ]; then
  export DISPLAY=:0
  log "DISPLAY was unset — exported DISPLAY=:0 for Chrome (Facebook non-headless mode)"
fi
# Wayland session bus — Chrome uses XWayland, but exporting helps avoid warnings
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  export WAYLAND_DISPLAY=wayland-0
fi

# ── Environment check ─────────────────────────────────────────────────────────
if [ ! -x "$VENV" ]; then
  log "ERROR: virtualenv not found at $VENV"
  log "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

cd "$SCRIPT_DIR"

# ── SQLite backup (before any writes) ────────────────────────────────────────
DB="$SCRIPT_DIR/output/leads.db"
if [ -f "$DB" ]; then
  cp "$DB" "${DB}.bak" && log "DB backup: leads.db.bak created" || log "WARN: DB backup failed"
fi

# ── Phase 1: Scraping ─────────────────────────────────────────────────────────
if [ "$DO_SCRAPE" = true ]; then
  log "=== SCRAPING START ==="
  log "Using: nice -n 10 ionice -c 3 (background-class I/O, low CPU priority)"

  # nice -n 10   → CPU priority 10 below normal (desktop stays snappy)
  # ionice -c 3  → disk I/O at idle class (won't compete with system I/O)
  nice -n 10 ionice -c 3 "$VENV" main.py >> "$LOG_FILE" 2>&1
  SCRAPE_EXIT=$?

  if [ $SCRAPE_EXIT -eq 0 ]; then
    log "=== SCRAPING COMPLETED OK ==="
  else
    log "=== SCRAPING FAILED (exit code $SCRAPE_EXIT) ==="
    log "Check $LOG_FILE for details. Dashboard > Sistema tab shows last run status."
  fi
fi

# ── Phase 2: Enrichment (separate Chrome session, lighter) ───────────────────
if [ "$DO_ENRICH" = true ]; then
  log "=== ENRICHMENT START (max=$ENRICH_MAX, min_score=$ENRICH_MIN_SCORE) ==="
  log "Visiting top profiles to extract bio, followers, email, website..."

  nice -n 10 ionice -c 3 "$VENV" enrich.py \
    --max "$ENRICH_MAX" \
    --min-score "$ENRICH_MIN_SCORE" \
    >> "$LOG_FILE" 2>&1
  ENRICH_EXIT=$?

  if [ $ENRICH_EXIT -eq 0 ]; then
    log "=== ENRICHMENT COMPLETED OK ==="
  else
    log "=== ENRICHMENT FAILED (exit code $ENRICH_EXIT) ==="
  fi
fi

log "=== SESSION DONE. Log saved to: $LOG_FILE ==="

# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULING — add one of these to crontab (crontab -e)
#
# RECOMMENDED CADENCE:
#
# Option A — Weekly (safest, minimal ban risk, enough for art/design niche)
#   Runs every Sunday at 3:00 AM while PC is idle.
#   0 3 * * 0  cd /home/zen/Documents/social-scrapp && ./run_scrape.sh
#
# Option B — Twice a week (more data, slightly higher activity)
#   Runs Wednesday + Sunday at 3:00 AM.
#   0 3 * * 0,3  cd /home/zen/Documents/social-scrapp && ./run_scrape.sh
#
# Option C — Enrich separately (lighter, mid-week top-up)
#   Full scrape on Sunday, enrich top profiles on Wednesday.
#   0 3 * * 0    cd /home/zen/Documents/social-scrapp && ./run_scrape.sh --scrape-only
#   0 3 * * 3    cd /home/zen/Documents/social-scrapp && ./run_scrape.sh --enrich-only
#
# For manual one-off runs use:
#   ./run_scrape.sh --scrape-only   # just collect leads
#   ./run_scrape.sh --enrich-only   # just visit top profiles
# ─────────────────────────────────────────────────────────────────────────────
