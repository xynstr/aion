"""
aion_memory.py — AionMemory Klasse (extrahiert aus aion.py)

Eigenständiges Modul ohne Abhängigkeit zu aion.py.
Wird von aion.py importiert: from aion_memory import AionMemory
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc


class AionMemory:
    def __init__(self, memory_file: Path, vectors_file: Path, max_entries: int = 300):
        self._memory_file  = memory_file
        self._vectors_file = vectors_file
        self._max_entries  = max_entries
        self._entries:     list[dict]        = []
        self._embed_cache: dict[str, list]   = {}   # id → embedding vector
        self._lock = asyncio.Lock()
        self._load()
        self._load_vectors()

    def _load(self):
        if self._memory_file.is_file():
            try:
                self._entries = json.loads(self._memory_file.read_text(encoding="utf-8"))
            except Exception:
                print(f"[AION] aion_memory.json korrupt — versuche Backup zu laden...")
                backups = sorted(self._memory_file.parent.glob(self._memory_file.name + ".bak_*"), reverse=True)
                for bak in backups:
                    try:
                        self._entries = json.loads(bak.read_text(encoding="utf-8"))
                        print(f"[AION] Memory aus Backup wiederhergestellt: {bak.name}")
                        return
                    except Exception:
                        continue
                print("[AION] Kein gültiges Memory-Backup gefunden — starte mit leerem Speicher.")
                self._entries = []

    def _save(self):
        self._memory_file.parent.mkdir(parents=True, exist_ok=True)
        self._memory_file.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(self, category: str, summary: str, lesson: str,
               success: bool = True, error: str = "", hint: str = ""):
        """Synchroner Record — thread-safe via asyncio.Lock wenn im Event-Loop aufgerufen.
        Für direkten Aufruf aus Plugins: _record_sync() nutzen."""
        try:
            loop = asyncio.get_running_loop()
            # Im Event-Loop: als Task einplanen (non-blocking)
            asyncio.ensure_future(self._record_async(category, summary, lesson, success, error, hint))
        except RuntimeError:
            # Kein laufender Loop (z.B. Startup) → direkt synchron
            self._record_sync(category, summary, lesson, success, error, hint)

    @staticmethod
    def _build_record(category: str, summary: str, lesson: str,
                      success: bool, error: str, hint: str) -> dict:
        return {
            "id":        str(uuid.uuid4())[:8],
            "timestamp": datetime.now(UTC).isoformat(),
            "category":  category,
            "success":   success,
            "summary":   summary[:250],
            "lesson":    lesson[:600],
            "error":     error[:300],
            "hint":      hint[:300],
        }

    def _record_sync(self, category: str, summary: str, lesson: str,
                     success: bool = True, error: str = "", hint: str = ""):
        """Synchrone Variante ohne Lock — nur für Startup/Thread-Kontext nutzen."""
        self._entries.append(self._build_record(category, summary, lesson, success, error, hint))
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        self._save()

    async def _record_async(self, category: str, summary: str, lesson: str,
                            success: bool = True, error: str = "", hint: str = ""):
        """Async Variante mit Lock — verhindert Race Conditions bei parallelen Writes."""
        async with self._lock:
            self._entries.append(self._build_record(category, summary, lesson, success, error, hint))
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]
            self._save()

    def get_context(self, query: str, max_entries: int = 8) -> str:
        if not self._entries:
            return ""
        keywords = {w for w in query.lower().split() if len(w) > 3}
        scored = []
        for e in self._entries:
            # Secure str() — older entries might accidentally contain lists
            summary = e.get("summary", "") or ""
            lesson  = e.get("lesson",  "") or ""
            combined = (str(summary) + str(lesson)).lower()
            score = sum(1 for w in keywords if w in combined)
            if not e.get("success"):
                score += 1
            scored.append((score, e))
        top = [e for sc, e in sorted(scored, key=lambda x: x[0], reverse=True)
               if sc > 0][:max_entries]
        if not top:
            return ""
        return self._format_memory_entries(top)

    @staticmethod
    def _format_memory_entries(entries: list) -> str:
        lines = ["[AION MEMORY — relevant insights]"]
        for e in entries:
            icon = "✅" if e.get("success") else "❌"
            ts   = e.get("timestamp", "")[:10]
            lines.append(f"{icon} [{ts}] {e.get('lesson', '')}")
            if e.get("hint"):
                lines.append(f"   → Tipp: {e['hint']}")
        lines.append("[END MEMORY]")
        return "\n".join(lines)

    # ── RAG / Semantic Search ──────────────────────────────────────────────────

    def _load_vectors(self):
        if self._vectors_file.is_file():
            try:
                self._embed_cache = json.loads(self._vectors_file.read_text(encoding="utf-8"))
            except Exception:
                self._embed_cache = {}

    def _save_vectors(self):
        try:
            self._vectors_file.write_text(
                json.dumps(self._embed_cache, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _cosine(a: list, b: list) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na  = sum(x * x for x in a) ** 0.5
        nb  = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    async def _embed(self, text: str) -> "list[float] | None":
        """Embedding via lokales Ollama (nomic-embed-text). None wenn nicht verfügbar."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": text[:2000]},
                )
                return r.json().get("embedding")
        except Exception:
            return None

    async def get_context_semantic(self, query: str, max_entries: int = 5) -> str:
        """RAG-Suche: semantische Ähnlichkeit via Ollama-Embeddings.
        Fällt automatisch auf Keyword-Matching zurück wenn Ollama nicht läuft."""
        if not self._entries:
            return ""

        qvec = await self._embed(query)
        if qvec is None:
            return self.get_context(query)          # Keyword-Fallback

        # Neue Einträge einbetten — max. 10 pro Turn damit kein Lag entsteht
        new_count = 0
        for entry in self._entries:
            eid = entry.get("id", "")
            if eid and eid not in self._embed_cache and new_count < 10:
                text = f"{entry.get('summary', '')} {entry.get('lesson', '')}"
                vec  = await self._embed(text)
                if vec:
                    self._embed_cache[eid] = vec
                    new_count += 1

        # Cosine-Scoring aller gecachten Einträge
        scored = []
        for entry in self._entries:
            eid = entry.get("id", "")
            if eid in self._embed_cache:
                sim = self._cosine(qvec, self._embed_cache[eid])
                scored.append((sim, entry))

        if not scored:
            return self.get_context(query)          # Keyword-Fallback

        scored.sort(key=lambda x: -x[0])
        top = [e for sim, e in scored[:max_entries] if sim > 0.35]

        if not top:
            return ""

        if new_count:
            self._save_vectors()

        return self._format_memory_entries(top)

    def summary(self, n: int = 15) -> str:
        if not self._entries:
            return "Noch keine Erkenntnisse gespeichert."
        recent = list(reversed(self._entries))[:n]
        lines  = [f"AION Memory ({len(self._entries)} entries)\n"]
        for e in recent:
            icon = "✅" if e.get("success") else "❌"
            ts   = e.get("timestamp", "")[:10]
            lines.append(f"{icon} [{ts}] [{e.get('category','?')}] {str(e.get('lesson',''))[:120]}")
        return "\n".join(lines)
