"""
Traffic Jam Service
===================
Generates dummy hourly road-traffic dataset, trains a classifier,
and returns route-level traffic-jam percentage.

This version adds a reliable background job-processing layer:
- in-memory queue
- bounded worker concurrency
- retry on transient failure
- central job state store
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from database import SessionLocal
from models.traffic_models import RoadTrafficObservation


@dataclass
class EdgeContext:
    edge_id: str
    road_type: str
    length_m: float


class TrafficJamService:
    """Dummy dataset + ML training + route risk inference."""

    def __init__(self):
        self._model = None
        self._road_type_code: dict[str, int] = {}
        self._jam_lookup: dict[tuple[str, int], int] = {}
        self._csv_path: Path | None = None
        self._initialized = False
        self._init_lock = threading.RLock()
        self._enable_model = str(
            os.getenv("TRAFFIC_ENABLE_MODEL", "0")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._dataset_auto_build = str(
            os.getenv("TRAFFIC_DATASET_AUTO_BUILD", "0")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._auto_start_workers = str(
            os.getenv("TRAFFIC_AUTO_START_WORKERS", "0")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._edge_prediction_cache: dict[tuple[str, int], tuple[float, int, float]] = (
            {}
        )
        self._edge_prediction_ttl_s: float = 300.0

        # Central route job store.
        self._route_predictions: dict[str, dict] = {}
        self._route_prediction_ttl_s: float = 900.0
        self._route_predictions_max: int = max(
            32,
            int(os.getenv("TRAFFIC_ROUTE_JOB_MAX", "128")),
        )
        self._max_edges_per_route_job: int = max(
            24,
            int(os.getenv("TRAFFIC_ROUTE_MAX_EDGES", "220")),
        )

        # Backward-compatibility dictionary (older tests clear this key).
        self._route_prediction_tasks: dict[str, asyncio.Task] = {}

        # Worker/queue controls.
        self._max_job_retries: int = max(
            0,
            int(os.getenv("TRAFFIC_JOB_MAX_RETRIES", "3")),
        )
        configured_workers = int(os.getenv("TRAFFIC_WORKER_COUNT", "1"))
        self._worker_count: int = max(1, min(2, configured_workers))
        self._queue_maxsize: int = max(
            32,
            int(os.getenv("TRAFFIC_QUEUE_MAXSIZE", "256")),
        )

        self._state_lock = threading.RLock()
        self._prediction_lock = threading.Lock()
        self._job_queue: asyncio.Queue[str] | None = None
        self._worker_tasks: list[asyncio.Task] = []
        self._retry_tasks: set[asyncio.Task] = set()
        self._worker_loop: asyncio.AbstractEventLoop | None = None

    def ensure_initialized(self, graph) -> None:
        if self._initialized:
            return
        if graph is None:
            return

        with self._init_lock:
            if self._initialized:
                return
            self.initialize_from_graph(graph)

    def initialize_from_graph(self, graph) -> None:
        """Ensure dataset exists, train from CSV, and build lookup cache."""
        if graph is None:
            return

        with self._init_lock:
            if self._initialized:
                return

            csv_path = self._find_existing_csv()

            if csv_path is None:
                try:
                    with SessionLocal() as db:
                        if self._dataset_auto_build:
                            expected_rows = graph.number_of_edges() * 24
                            existing_rows = db.query(RoadTrafficObservation).count()
                            if existing_rows < expected_rows:
                                self._regenerate_dataset(db, graph)
                            csv_path = self._ensure_dataset_csv(db)
                        else:
                            csv_path = self._ensure_dataset_csv(db)
                except Exception:
                    csv_path = self._find_existing_csv()

            self._csv_path = csv_path
            if csv_path is not None:
                self._load_jam_lookup_from_csv(csv_path)

            if self._enable_model and csv_path is not None:
                self._train_from_csv(csv_path)
            else:
                self._model = None
                self._edge_prediction_cache = {}

            self._initialized = True
            return

    async def start_workers(self, worker_count: int | None = None) -> None:
        """Start queue workers for traffic jobs (idempotent per event loop)."""
        loop = asyncio.get_running_loop()
        if worker_count is not None:
            self._worker_count = max(1, min(2, int(worker_count)))

        self._ensure_worker_loop(loop)

        # Recover jobs that were pending/running if workers restarted.
        with self._state_lock:
            recoverable_ids: list[str] = []
            for route_id, job in self._route_predictions.items():
                status = str(job.get("status") or "")
                if status in {"pending", "running"}:
                    job["status"] = "pending"
                    job["queued"] = False
                    self._touch_job_locked(job)
                    recoverable_ids.append(route_id)

            for route_id in recoverable_ids:
                self._enqueue_job_locked(route_id)

    async def stop_workers(self) -> None:
        """Stop worker/retry tasks cleanly during app shutdown."""
        with self._state_lock:
            worker_tasks = [task for task in self._worker_tasks if not task.done()]
            retry_tasks = [task for task in self._retry_tasks if not task.done()]
            self._worker_tasks = []
            self._retry_tasks = set()
            self._worker_loop = None
            self._job_queue = None

        for task in worker_tasks + retry_tasks:
            with contextlib.suppress(RuntimeError):
                task.cancel()

        for task in worker_tasks + retry_tasks:
            with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                await task

    def _ensure_worker_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Ensure queue and workers exist for current loop."""
        with self._state_lock:
            alive = [task for task in self._worker_tasks if not task.done()]
            same_loop = self._worker_loop is loop

            if (
                same_loop
                and self._job_queue is not None
                and len(alive) >= self._worker_count
            ):
                self._worker_tasks = alive[: self._worker_count]
                return

            if not same_loop:
                for task in alive:
                    with contextlib.suppress(RuntimeError):
                        task.cancel()
                alive = []
                self._job_queue = asyncio.Queue(maxsize=self._queue_maxsize)
                self._worker_loop = loop

            if self._job_queue is None:
                self._job_queue = asyncio.Queue(maxsize=self._queue_maxsize)
                self._worker_loop = loop

            self._worker_tasks = alive
            next_index = len(self._worker_tasks)
            while len(self._worker_tasks) < self._worker_count:
                worker_task = loop.create_task(
                    self._worker_loop_run(next_index),
                    name=f"traffic-worker-{next_index}",
                )
                self._worker_tasks.append(worker_task)
                next_index += 1

    async def _worker_loop_run(self, worker_index: int) -> None:
        del worker_index
        while True:
            queue = self._job_queue
            if queue is None:
                await asyncio.sleep(0.05)
                continue

            route_id = await queue.get()
            try:
                with self._state_lock:
                    job = self._route_predictions.get(route_id)
                    if job is None:
                        continue

                    job["queued"] = False
                    if str(job.get("status") or "") != "pending":
                        continue

                    job["status"] = "running"
                    job["error"] = None
                    self._touch_job_locked(job)
                    edge_contexts = list(job.get("edge_contexts") or [])
                    hour_of_day = job.get("hour_of_day")

                result = await asyncio.to_thread(
                    self.predict_route_jam,
                    edge_contexts,
                    hour_of_day,
                )

                with self._state_lock:
                    job = self._route_predictions.get(route_id)
                    if job is None:
                        continue
                    job["status"] = "completed"
                    job["result"] = result
                    job["error"] = None
                    self._touch_job_locked(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                retry_delay_s = None
                with self._state_lock:
                    job = self._route_predictions.get(route_id)
                    if job is None:
                        continue

                    retry_count = int(job.get("retry_count") or 0) + 1
                    job["retry_count"] = retry_count
                    job["error"] = str(exc)
                    max_retries = int(job.get("max_retries") or self._max_job_retries)

                    if retry_count <= max_retries:
                        job["status"] = "pending"
                        self._touch_job_locked(job)
                        retry_delay_s = min(2.0, 0.15 * (2 ** max(0, retry_count - 1)))
                    else:
                        job["status"] = "failed"
                        self._touch_job_locked(job)

                if retry_delay_s is not None:
                    self._schedule_retry(route_id, retry_delay_s)
            finally:
                queue.task_done()

    def _schedule_retry(self, route_id: str, delay_s: float) -> None:
        loop = self._worker_loop
        if loop is None:
            with self._state_lock:
                job = self._route_predictions.get(route_id)
                if job is not None:
                    job["status"] = "failed"
                    job["error"] = "worker loop unavailable"
                    self._touch_job_locked(job)
            return

        task = loop.create_task(self._retry_after_delay(route_id, delay_s))
        with self._state_lock:
            self._retry_tasks.add(task)

        def _cleanup_retry_task(done_task: asyncio.Task) -> None:
            with self._state_lock:
                self._retry_tasks.discard(done_task)

        task.add_done_callback(_cleanup_retry_task)

    async def _retry_after_delay(self, route_id: str, delay_s: float) -> None:
        await asyncio.sleep(max(0.01, float(delay_s)))
        with self._state_lock:
            job = self._route_predictions.get(route_id)
            if job is None or str(job.get("status") or "") != "pending":
                return
            self._enqueue_job_locked(route_id)

    def _touch_job_locked(self, job: dict) -> None:
        job["updated_at"] = time.time()
        job["updated_monotonic"] = time.monotonic()

    def _enqueue_job_locked(self, route_id: str) -> bool:
        job = self._route_predictions.get(route_id)
        if job is None:
            return False

        if bool(job.get("queued", False)):
            return True

        if self._job_queue is None:
            job["status"] = "failed"
            job["error"] = "traffic queue unavailable"
            self._touch_job_locked(job)
            return False

        try:
            self._job_queue.put_nowait(route_id)
            job["queued"] = True
            self._touch_job_locked(job)
            return True
        except asyncio.QueueFull:
            job["status"] = "failed"
            job["error"] = "traffic queue overloaded"
            self._touch_job_locked(job)
            return False

    def _to_public_status(self, internal_status: str) -> str:
        if internal_status in {"pending", "running"}:
            return "loading"
        if internal_status == "completed":
            return "ready"
        return "failed"

    def _compact_edge_contexts(self, edge_contexts: list[dict]) -> list[dict]:
        compact: list[dict] = []
        for edge in edge_contexts:
            edge_id = str(edge.get("edge_id") or "").strip()
            if not edge_id:
                continue
            compact.append(
                {
                    "edge_id": edge_id,
                    "road_type": str(edge.get("road_type") or "unknown"),
                    "length_m": float(edge.get("length_m") or 0.0),
                }
            )

        max_edges = max(1, int(self._max_edges_per_route_job))
        if len(compact) <= max_edges:
            return compact

        # Keep a representative spread across long routes.
        sample: list[dict] = [compact[0]]
        span = len(compact) - 1
        if max_edges > 1:
            for i in range(1, max_edges - 1):
                idx = int((i * span) / max(1, (max_edges - 1)))
                sample.append(compact[idx])
            sample.append(compact[-1])
        return sample[:max_edges]

    def _enforce_route_prediction_limit_locked(self) -> bool:
        limit = max(1, int(self._route_predictions_max))
        if len(self._route_predictions) < limit:
            return True

        terminal_jobs = [
            (
                float(item.get("updated_monotonic") or 0.0),
                route_id,
            )
            for route_id, item in self._route_predictions.items()
            if str(item.get("status") or "") in {"completed", "failed"}
        ]
        terminal_jobs.sort(key=lambda t: t[0])

        while len(self._route_predictions) >= limit and terminal_jobs:
            _, stale_route_id = terminal_jobs.pop(0)
            self._route_predictions.pop(stale_route_id, None)

        return len(self._route_predictions) < limit

    def start_route_prediction(
        self,
        edge_contexts: list[dict],
        hour_of_day: int | None = None,
    ) -> dict:
        """Queue non-blocking traffic prediction and return immediate tracking metadata."""
        self._evict_expired_route_predictions()

        route_id = f"route_{uuid.uuid4().hex[:12]}"
        now_wall = time.time()
        now_mono = time.monotonic()
        compact_contexts = self._compact_edge_contexts(edge_contexts)

        with self._state_lock:
            if not self._enforce_route_prediction_limit_locked():
                self._route_predictions[route_id] = {
                    "status": "failed",
                    "result": None,
                    "error": "traffic job store limit reached",
                    "retry_count": 0,
                    "max_retries": self._max_job_retries,
                    "edge_contexts": [],
                    "hour_of_day": hour_of_day,
                    "queued": False,
                    "created_at": now_wall,
                    "updated_at": now_wall,
                    "updated_monotonic": now_mono,
                }
                return {
                    "route_id": route_id,
                    "status": "failed",
                    "data": None,
                }

            if not compact_contexts:
                self._route_predictions[route_id] = {
                    "status": "completed",
                    "result": None,
                    "error": None,
                    "retry_count": 0,
                    "max_retries": self._max_job_retries,
                    "edge_contexts": [],
                    "hour_of_day": hour_of_day,
                    "queued": False,
                    "created_at": now_wall,
                    "updated_at": now_wall,
                    "updated_monotonic": now_mono,
                }
                return {
                    "route_id": route_id,
                    "status": "ready",
                    "data": None,
                }

            self._route_predictions[route_id] = {
                "status": "pending",
                "result": None,
                "error": None,
                "retry_count": 0,
                "max_retries": self._max_job_retries,
                "edge_contexts": compact_contexts,
                "hour_of_day": hour_of_day,
                "queued": False,
                "created_at": now_wall,
                "updated_at": now_wall,
                "updated_monotonic": now_mono,
            }

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (script/CLI path): compute synchronously as a fallback.
            try:
                data = self.predict_route_jam(edge_contexts, hour_of_day=hour_of_day)
                with self._state_lock:
                    job = self._route_predictions.get(route_id)
                    if job is not None:
                        job["status"] = "completed"
                        job["result"] = data
                        job["error"] = None
                        self._touch_job_locked(job)
            except Exception as exc:
                with self._state_lock:
                    job = self._route_predictions.get(route_id)
                    if job is not None:
                        job["status"] = "failed"
                        job["retry_count"] = int(
                            job.get("max_retries") or self._max_job_retries
                        )
                        job["error"] = str(exc)
                        self._touch_job_locked(job)
        else:
            with self._state_lock:
                same_loop = self._worker_loop is loop and self._job_queue is not None

            if same_loop:
                with self._state_lock:
                    self._enqueue_job_locked(route_id)
            elif self._auto_start_workers:
                self._ensure_worker_loop(loop)
                with self._state_lock:
                    self._enqueue_job_locked(route_id)
            else:
                try:
                    data = self.predict_route_jam(
                        compact_contexts, hour_of_day=hour_of_day
                    )
                    with self._state_lock:
                        job = self._route_predictions.get(route_id)
                        if job is not None:
                            job["status"] = "completed"
                            job["result"] = data
                            job["error"] = None
                            self._touch_job_locked(job)
                except Exception as exc:
                    with self._state_lock:
                        job = self._route_predictions.get(route_id)
                        if job is not None:
                            job["status"] = "failed"
                            job["retry_count"] = int(
                                job.get("max_retries") or self._max_job_retries
                            )
                            job["error"] = str(exc)
                            self._touch_job_locked(job)

        with self._state_lock:
            current = self._route_predictions.get(route_id, {})
            public_status = self._to_public_status(
                str(current.get("status") or "pending")
            )
            return {
                "route_id": route_id,
                "status": public_status,
                "data": current.get("result") if public_status == "ready" else None,
            }

    def get_route_prediction(self, route_id: str) -> dict | None:
        """Return job + public status for a traffic prediction route_id."""
        self._evict_expired_route_predictions()
        with self._state_lock:
            item = self._route_predictions.get(route_id)
            if item is None:
                return None

            internal_status = str(item.get("status") or "pending")
            public_status = self._to_public_status(internal_status)
            payload = {
                "route_id": route_id,
                "status": public_status,
                "job_status": internal_status,
                "retry_count": int(item.get("retry_count") or 0),
                "max_retries": int(item.get("max_retries") or self._max_job_retries),
                "updated_at": float(item.get("updated_at") or time.time()),
            }
            if public_status == "ready":
                payload["data"] = item.get("result")
            elif public_status == "failed":
                payload["error"] = str(item.get("error") or "traffic prediction failed")
            return payload

    def _evict_expired_route_predictions(self):
        now = time.monotonic()
        with self._state_lock:
            stale_ids: list[str] = []
            for route_id, item in self._route_predictions.items():
                status = str(item.get("status") or "")
                # Preserve active jobs; evict only terminal states.
                if status not in {"completed", "failed"}:
                    continue
                updated_monotonic = float(item.get("updated_monotonic") or now)
                if (now - updated_monotonic) > self._route_prediction_ttl_s:
                    stale_ids.append(route_id)

            for route_id in stale_ids:
                self._route_predictions.pop(route_id, None)

    def _evict_expired_edge_cache(self):
        now = time.monotonic()
        with self._state_lock:
            stale_keys = [
                key
                for key, (_prob, _level, ts) in self._edge_prediction_cache.items()
                if (now - ts) > self._edge_prediction_ttl_s
            ]
            for key in stale_keys:
                self._edge_prediction_cache.pop(key, None)

    def predict_route_jam(
        self,
        edge_contexts: list[dict],
        hour_of_day: int | None = None,
    ) -> dict | None:
        """Predict combined traffic-jam percentage for route edges at a given hour."""
        with self._prediction_lock:
            if not edge_contexts:
                return None

            if (
                self._model is None
                and self._enable_model
                and self._csv_path is not None
            ):
                self._train_from_csv(self._csv_path)
                self._load_jam_lookup_from_csv(self._csv_path)

            model = self._model

            self._evict_expired_edge_cache()

            hour = int(datetime.now().hour if hour_of_day is None else hour_of_day) % 24

            analyzed = 0
            heavy = 0
            moderate = 0
            low = 0
            edge_prob_sum = 0.0

            pending_features: list[list[float]] = []
            pending_meta: list[tuple[tuple[str, int], int]] = []
            resolved_edges: list[tuple[float, int]] = []

            for edge in edge_contexts:
                edge_id = str(edge.get("edge_id") or "")
                if not edge_id:
                    continue

                road_type = str(edge.get("road_type") or "unknown")
                length_m = float(edge.get("length_m") or 0.0)
                cache_key = (edge_id, hour)

                cached = self._edge_prediction_cache.get(cache_key)
                if cached is not None:
                    cached_prob, cached_level, cached_ts = cached
                    if (time.monotonic() - cached_ts) <= self._edge_prediction_ttl_s:
                        resolved_edges.append((float(cached_prob), int(cached_level)))
                        continue
                    self._edge_prediction_cache.pop(cache_key, None)

                jam_level = self._jam_lookup.get((edge_id, hour))
                if jam_level is None:
                    jam_level = self._dummy_level(edge_id, road_type, hour)

                if model is None:
                    edge_jam_prob = {1: 0.20, 2: 0.58, 3: 0.90}.get(
                        int(jam_level), 0.50
                    )
                    self._edge_prediction_cache[cache_key] = (
                        float(edge_jam_prob),
                        int(jam_level),
                        time.monotonic(),
                    )
                    resolved_edges.append((float(edge_jam_prob), int(jam_level)))
                    continue

                pending_features.append(
                    [
                        float(hour),
                        float(self._edge_hash(edge_id)),
                        float(self._road_type_to_code(road_type)),
                        float(self._length_bucket(length_m)),
                    ]
                )
                pending_meta.append((cache_key, int(jam_level)))

            if pending_features and model is not None:
                x = np.asarray(pending_features, dtype=float)
                class_probs = model.predict_proba(x)
                classes = list(model.classes_)
                mod_idx = classes.index(2) if 2 in classes else None
                heavy_idx = classes.index(3) if 3 in classes else None
                now = time.monotonic()

                for i, probs in enumerate(class_probs):
                    cache_key, jam_level = pending_meta[i]
                    prob_mod = float(probs[mod_idx]) if mod_idx is not None else 0.0
                    prob_heavy = (
                        float(probs[heavy_idx]) if heavy_idx is not None else 0.0
                    )
                    model_jam_prob = prob_mod + prob_heavy

                    level_factor = {1: 0.25, 2: 0.60, 3: 0.90}.get(jam_level, 0.50)
                    edge_jam_prob = 0.5 * model_jam_prob + 0.5 * level_factor
                    edge_jam_prob = max(0.01, min(0.99, edge_jam_prob))

                    self._edge_prediction_cache[cache_key] = (
                        float(edge_jam_prob),
                        int(jam_level),
                        now,
                    )
                    resolved_edges.append((float(edge_jam_prob), int(jam_level)))

            for edge_jam_prob, jam_level in resolved_edges:
                if jam_level >= 3:
                    heavy += 1
                elif jam_level == 2:
                    moderate += 1
                else:
                    low += 1
                edge_prob_sum += edge_jam_prob
                analyzed += 1

            if analyzed == 0:
                return None

            route_jam_prob = edge_prob_sum / float(analyzed)
            confidence = min(1.0, 0.60 + 0.40 * min(1.0, analyzed / 16.0))

            return {
                "hour_of_day": hour,
                "route_jam_chance_pct": round(route_jam_prob * 100.0, 2),
                "edges_analyzed": analyzed,
                "heavy_edges": heavy,
                "moderate_edges": moderate,
                "low_edges": low,
                "confidence": round(confidence, 3),
            }

    def _regenerate_dataset(self, db: Session, graph) -> None:
        """Build a complete per-road, per-hour dummy dataset and persist to DB + CSV."""
        db.query(RoadTrafficObservation).delete()
        db.commit()

        rows: list[RoadTrafficObservation] = []
        csv_rows: list[list[str | int | float]] = []

        for u, v, key, data in graph.edges(keys=True, data=True):
            edge_id = f"{u}->{v}:{key}"
            road_type = self._road_type(data)
            length_m = float(data.get("length") or 0.0)

            for hour in range(24):
                level = self._dummy_level(edge_id, road_type, hour)
                label = {1: "low", 2: "moderate", 3: "heavy"}[level]

                rows.append(
                    RoadTrafficObservation(
                        edge_id=edge_id,
                        road_type=road_type,
                        length_m=length_m,
                        hour_of_day=hour,
                        jam_level=level,
                        jam_label=label,
                    )
                )
                csv_rows.append(
                    [edge_id, road_type, round(length_m, 3), hour, level, label]
                )

        db.bulk_save_objects(rows)
        db.commit()
        self._write_csv(csv_rows)

    def _ensure_dataset_csv(self, db: Session) -> Path | None:
        """Return a dataset CSV path; export from DB if a local CSV does not already exist."""
        existing = self._find_existing_csv()
        if existing is not None:
            return existing

        records = db.query(RoadTrafficObservation).all()
        if not records:
            return None

        csv_rows = [
            [
                rec.edge_id,
                rec.road_type,
                round(float(rec.length_m), 3),
                int(rec.hour_of_day),
                int(rec.jam_level),
                rec.jam_label,
            ]
            for rec in records
        ]
        return self._write_csv(csv_rows)

    def _train_from_csv(self, csv_path: Path) -> None:
        """Train a 3-class classifier (Low/Moderate/Heavy) from dataset CSV."""
        import pandas as pd
        from sklearn.ensemble import RandomForestClassifier

        if not csv_path.exists():
            self._model = None
            self._edge_prediction_cache = {}
            return

        df = pd.read_csv(csv_path)
        if df.empty:
            self._model = None
            self._edge_prediction_cache = {}
            return

        x = np.column_stack(
            [
                df["hour_of_day"].astype(float).to_numpy(),
                df["edge_id"].astype(str).map(self._edge_hash).astype(float).to_numpy(),
                df["road_type"]
                .astype(str)
                .map(self._road_type_to_code)
                .astype(float)
                .to_numpy(),
                df["length_m"]
                .astype(float)
                .map(self._length_bucket)
                .astype(float)
                .to_numpy(),
            ]
        )
        y = df["jam_level"].astype(int).to_numpy()

        model = RandomForestClassifier(
            n_estimators=64,
            max_depth=8,
            min_samples_split=6,
            min_samples_leaf=4,
            random_state=42,
            n_jobs=1,
        )
        model.fit(x, y)
        self._model = model
        self._edge_prediction_cache = {}

    def _load_jam_lookup_from_csv(self, csv_path: Path) -> None:
        """Cache jam levels from CSV keyed by (edge_id, hour)."""
        import pandas as pd

        self._jam_lookup = {}
        self._edge_prediction_cache = {}
        if not csv_path.exists():
            return

        df = pd.read_csv(csv_path, usecols=["edge_id", "hour_of_day", "jam_level"])
        for row in df.itertuples(index=False):
            self._jam_lookup[(str(row.edge_id), int(row.hour_of_day))] = int(
                row.jam_level
            )

    def _road_type(self, edge_data: dict) -> str:
        road = edge_data.get("road_type") or edge_data.get("highway") or "unknown"
        if isinstance(road, (list, tuple)):
            return str(road[0]) if road else "unknown"
        return str(road)

    def _dummy_level(self, edge_id: str, road_type: str, hour: int) -> int:
        """Generate deterministic dummy level (1/2/3) with rush-hour bias."""
        seed = self._stable_int(f"{edge_id}:{road_type}:{hour}") % 100

        if 7 <= hour <= 10 or 17 <= hour <= 20:
            if seed < 50:
                return 3
            if seed < 85:
                return 2
            return 1

        if 11 <= hour <= 16:
            if seed < 25:
                return 3
            if seed < 70:
                return 2
            return 1

        if seed < 12:
            return 3
        if seed < 48:
            return 2
        return 1

    def _dataset_candidates(self) -> list[Path]:
        return [
            Path(__file__).resolve().parents[1] / "data" / "traffic_dummy_dataset.csv",
            Path("/app/data/osm_cache/traffic_dummy_dataset.csv"),
            Path("/tmp/traffic_dummy_dataset.csv"),
        ]

    def _find_existing_csv(self) -> Path | None:
        for path in self._dataset_candidates():
            if path.exists() and path.stat().st_size > 0:
                return path
        return None

    def _write_csv(self, rows: list[list[str | int | float]]) -> Path | None:
        candidate_paths = self._dataset_candidates()

        for csv_path in candidate_paths:
            try:
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "edge_id",
                            "road_type",
                            "length_m",
                            "hour_of_day",
                            "jam_level",
                            "jam_label",
                        ]
                    )
                    writer.writerows(rows)
                return csv_path
            except PermissionError:
                continue

        return None

    def _edge_hash(self, edge_id: str) -> int:
        return self._stable_int(edge_id) % 10000

    def _road_type_to_code(self, road_type: str) -> int:
        key = road_type or "unknown"
        if key not in self._road_type_code:
            self._road_type_code[key] = len(self._road_type_code) + 1
        return self._road_type_code[key]

    def _length_bucket(self, length_m: float) -> int:
        return int(max(0.0, min(1000.0, math.floor(length_m / 25.0))))

    def _stable_int(self, text: str) -> int:
        return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:12], 16)


traffic_jam_service = TrafficJamService()
