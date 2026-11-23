"""Separate queue/process so note OCR never occupies the itinerary worker."""

from celery import Celery

from ..config import settings
from . import jobs

celery = Celery("travel_notes", broker=settings.broker_url)
celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_ignore_result=True,
    task_default_queue=jobs.QUEUE,
    task_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=2,
    broker_transport_options={"visibility_timeout": 900, "socket_timeout": 2, "socket_connect_timeout": 2},
)


@celery.task(name="notes.process")
def process_note(ident):
    jobs.process(ident)
