import sqlite3
import uuid
from datetime import datetime, timezone

from schemas import Category, Priority, Teams, TicketOutput, HumanRouted

DB_PATH = "tickets.db"

CONFIDENCE_THRESHOLD = 60


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable accessing columns by names
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY,
                input TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                team TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                reasoning TEXT NOT NULL,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'llm',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def insert_ticket(ticket: TicketOutput, source: str ) -> str:
    """Persist a freshly routed ticket. Status is derived from confidence:
    below the threshold it's set aside (not shown to any team), otherwise
    it lands in the unified log and its team's queue."""
    ticket_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    status = "routed" if ticket.confidence >= CONFIDENCE_THRESHOLD else "below_threshold"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tickets
                (id, input, category, priority, team, confidence, reasoning, status, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                ticket.input,
                ticket.category.value,
                ticket.priority.value,
                ticket.team.value,
                ticket.confidence,
                ticket.reasoning,
                status,
                source,
                now,
                now,
            ),
        )
    return ticket_id


def flag_to_admin(ticket_id: str) -> None:
    """A team marks a routed ticket as wrong or not theirs; admin picks it up next."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
            ("flagged_to_admin", now, ticket_id),
        )


def boost_confidence(ticket_id: str, new_confidence: int = 90) -> None:
    """A team confirms a low-confidence route was actually correct.
    Status is left untouched (the ticket was already 'routed' and stays
    that way) — only confidence and source change."""
    if not 0 <= new_confidence <= 100:
        raise ValueError("new_confidence must be between 0 and 100")

    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE tickets SET confidence = ?, source = ?, updated_at = ? WHERE id = ?",
            (new_confidence, "confidence_boosted", now, ticket_id),
        )


def admin_correct(
    ticket_id: str,
    input_text: str,
    category: Category,
    priority: Priority,
    team: Teams,
    reasoning: str,
) -> None:
    """Admin reviews a flagged ticket and sets it to what it should have been.
    Routed back through HumanRouted so the correction is validated the same
    way an LLM-produced ticket would be, before it ever reaches the DB.
    Status goes back to 'routed' (so the corrected team actually sees it in
    their queue) while source records 'admin_corrected' permanently, for
    Phase 2 semantic memory to find it regardless of what status does next."""
    corrected = HumanRouted(
        input=input_text,
        category=category,
        priority=priority,
        team=team,
        reasoning=reasoning,
    )

    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE tickets
            SET category = ?, priority = ?, team = ?, reasoning = ?,
                confidence = ?, status = 'routed', source = 'admin_corrected', updated_at = ?
            WHERE id = ?
            """,
            (
                corrected.category.value,
                corrected.priority.value,
                corrected.team.value,
                corrected.reasoning,
                corrected.confidence,
                now,
                ticket_id,
            ),
        )

def get_unified_log() -> list[dict]:

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]

def get_team_queue(team: Teams) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE team = ? AND status = 'routed' ORDER BY created_at DESC",
            (team.value,),
        ).fetchall()
    return [dict(row) for row in rows]

def get_admin_queue() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE status = 'flagged_to_admin' ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]

def get_semantic_memory_candidates() -> list[dict]:
    """Rows a human has actually validated — the only source Phase 2 should
    learn from. Filtered purely by `source`, independent of current status,
    so a re-routed admin correction still shows up here even after its
    status has moved on to 'routed' again."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE source IN ('admin_corrected', 'confidence_boosted') ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]