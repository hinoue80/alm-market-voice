from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, JSON,
    ForeignKey, UniqueConstraint, create_engine, event
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.pool import NullPool
from app.config import settings


def _make_engine():
    url = settings.database_url
    if url.startswith("sqlite"):
        # SQLite with NullPool: each thread gets its own connection — no pool contention.
        # WAL mode allows concurrent readers with one writer, so this is safe.
        eng = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        # Enable WAL and foreign keys on every new connection
        @event.listens_for(eng, "connect")
        def _set_pragmas(conn, _):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
        return eng
    # PostgreSQL / any other DB — standard pool with pre-ping
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Source definition ────────────────────────────────────────────────────────

class Source(Base):
    """A registered signal source."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True)
    # Types: practitioner_community | trade_media | rss | practitioner_pub | conference
    source_type = Column(String(40), nullable=False)
    url = Column(String(500), nullable=False)
    enabled = Column(Integer, default=1)               # 1=on, 0=off
    created_at = Column(DateTime, default=datetime.utcnow)

    signals = relationship("Signal", back_populates="source")


# ── Raw signal ───────────────────────────────────────────────────────────────

class Signal(Base):
    """A single piece of content fetched from a source."""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    external_id = Column(String(255))
    title = Column(String(500))
    body = Column(Text)
    url = Column(String(1000))
    published_at = Column(DateTime)
    collected_at = Column(DateTime, default=datetime.utcnow)

    # ── Original enrichment fields ──────────────────────────────────────────
    topics = Column(JSON, default=list)        # ["predictive maintenance", ...]
    sentiment = Column(String(20))             # positive|negative|neutral
    relevance_score = Column(Float)            # 0.0–1.0
    signal_type = Column(String(40))           # demand|complaint|analyst|general
    enriched = Column(Integer, default=0)      # 0=raw, 1=LLM-enriched

    # ── New demand-signal enrichment fields (Phase 2) ───────────────────────
    demand_signal = Column(String(200))        # 4-8 word pattern name
    problem = Column(Text)                     # what the practitioner is struggling with
    desired_outcome = Column(Text)             # business/operational result they want
    approach = Column(Text)                    # what they're trying or asking about
    persona = Column(String(200))              # role/title inferred
    industry = Column(String(100))             # Manufacturing, Utilities, etc.
    org_type = Column(String(40))              # asset_owner|vendor|consultant|unknown
    author_type = Column(String(40))           # practitioner|vendor|unknown
    evidence_weight = Column(Integer)          # 0–5 practitioner evidence score

    source = relationship("Source", back_populates="signals")

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_signal_source_external"),
        UniqueConstraint("url", name="uq_signal_url"),
    )


# ── Demand Signal aggregation ────────────────────────────────────────────────

class DemandSignal(Base):
    """
    Aggregated demand signal pattern derived from multiple raw signals.
    Built by rolling up signals that share the same demand_signal label.
    """
    __tablename__ = "demand_signals"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(200), nullable=False, unique=True)  # e.g. "reactive-to-planned maintenance transition"
    signal_count = Column(Integer, default=0)       # number of raw signals sharing this label
    evidence_weight_avg = Column(Float, default=0)  # average evidence_weight across signals
    industries = Column(JSON, default=list)         # distinct industries mentioning this signal
    personas = Column(JSON, default=list)           # distinct personas
    source_types = Column(JSON, default=list)       # distinct source types
    sample_problems = Column(JSON, default=list)    # up to 3 representative problem statements
    sample_outcomes = Column(JSON, default=list)    # up to 3 representative desired outcomes
    last_seen = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Topic aggregation ────────────────────────────────────────────────────────

class TopicSummary(Base):
    """Weekly rollup of topic mention counts across sources."""
    __tablename__ = "topic_summaries"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(200), nullable=False)
    week_start = Column(DateTime, nullable=False)
    mention_count = Column(Integer, default=0)
    avg_sentiment_score = Column(Float)
    source_breakdown = Column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("topic", "week_start", name="uq_topic_week"),
    )


def init_db():
    """Create all tables and seed default sources."""
    Base.metadata.create_all(bind=engine)
    _seed_sources()


def _seed_sources():
    db = SessionLocal()
    try:
        existing = db.query(Source).count()
        if existing > 0:
            return

        default_sources = [
            # Practitioner communities
            Source(name="Reddit r/facilitymanagement", source_type="practitioner_community",
                   url="https://www.reddit.com/r/facilitymanagement/top/.json?t=week&limit=25"),
            Source(name="Reddit r/EAM", source_type="practitioner_community",
                   url="https://www.reddit.com/r/EAM/top/.json?t=week&limit=25"),
            Source(name="Reddit r/assetmanagement", source_type="practitioner_community",
                   url="https://www.reddit.com/r/assetmanagement/top/.json?t=week&limit=25"),

            # Analyst RSS feeds
            Source(name="Gartner Blog", source_type="rss",
                   url="https://news.google.com/rss/search?q=gartner+enterprise+asset+management+EAM&hl=en-US&gl=US&ceid=US:en"),
            Source(name="IDC Blog", source_type="rss",
                   url="https://news.google.com/rss/search?q=IDC+enterprise+asset+management+industrial&hl=en-US&gl=US&ceid=US:en"),
            Source(name="Verdantix", source_type="rss",
                   url="https://news.google.com/rss/search?q=verdantix+asset+management+EAM&hl=en-US&gl=US&ceid=US:en"),
            Source(name="ARC Advisory", source_type="rss",
                   url="https://www.arcweb.com/rss.xml"),

            # Trade media
            Source(name="Plant Engineering", source_type="trade_media",
                   url="https://www.plantengineering.com/rss/all"),
            Source(name="Control Engineering", source_type="trade_media",
                   url="https://news.google.com/rss/search?q=control+engineering+industrial+automation+asset+maintenance&hl=en-US&gl=US&ceid=US:en"),
            Source(name="T&D World", source_type="trade_media",
                   url="https://news.google.com/rss/search?q=transmission+distribution+utility+asset+management+maintenance&hl=en-US&gl=US&ceid=US:en"),
            Source(name="Facilitiesnet", source_type="trade_media",
                   url="https://news.google.com/rss/search?q=facilities+management+maintenance+asset+management&hl=en-US&gl=US&ceid=US:en"),
            Source(name="Utility Dive", source_type="trade_media",
                   url="https://www.utilitydive.com/feeds/news/"),
            Source(name="EHS Today", source_type="trade_media",
                   url="https://news.google.com/rss/search?q=EHS+safety+industrial+maintenance&hl=en-US&gl=US&ceid=US:en"),

            # Practitioner publications
            Source(name="Plant Services", source_type="practitioner_pub",
                   url="https://news.google.com/rss/search?q=plant+services+maintenance+reliability&hl=en-US&gl=US&ceid=US:en"),
            Source(name="Reliable Plant", source_type="practitioner_pub",
                   url="https://news.google.com/rss/search?q=reliable+plant+maintenance+reliability+practitioner&hl=en-US&gl=US&ceid=US:en"),
            Source(name="Maintworld", source_type="practitioner_pub",
                   url="https://news.google.com/rss/search?q=maintworld+maintenance+reliability&hl=en-US&gl=US&ceid=US:en"),
            Source(name="Maintenance World", source_type="practitioner_pub",
                   url="https://news.google.com/rss/search?q=maintenance+world+reliability+asset+management&hl=en-US&gl=US&ceid=US:en"),
            Source(name="Reliabilityweb / IMC", source_type="practitioner_pub",
                   url="https://news.google.com/rss/search?q=reliabilityweb+maintenance+reliability&hl=en-US&gl=US&ceid=US:en"),
            Source(name="Asset Mgmt & Maintenance Journal", source_type="practitioner_pub",
                   url="https://news.google.com/rss/search?q=asset+management+maintenance+journal+practitioner&hl=en-US&gl=US&ceid=US:en"),

            # Conference programs (Tavily crawl — seasonal)
            Source(name="SMRP Annual Conference", source_type="conference",
                   url="https://www.smrp.org/conference"),
            Source(name="MAINSTREAM Summit", source_type="conference",
                   url="https://www.maintenancesummit.com/sessions"),
            Source(name="Reliable Plant Conference", source_type="conference",
                   url="https://www.reliableplant.com/conference"),
            Source(name="IMC / Reliabilityweb Conference", source_type="conference",
                   url="https://reliabilityweb.com/imc"),
            Source(name="IAM Conference", source_type="conference",
                   url="https://theiam.org/events"),
        ]

        for s in default_sources:
            db.add(s)
        db.commit()
    finally:
        db.close()
