"""Recoverable, single-job queue worker foundation. Not yet wired to HTTP intake.

A heartbeat keeps ownership while a long video job executes. An expired lease
must never be acknowledged as success. Caller supplies the actual job handler.
"""
import threading
import uuid
from durable_queue import DurableQueue


def run_once(queue, handler, *, worker_id=None, lease_seconds=120, heartbeat_seconds=30):
    if heartbeat_seconds <= 0 or heartbeat_seconds >= lease_seconds:
        raise ValueError('Heartbeat must be positive and shorter than lease')
    claim = queue.claim(worker_id or uuid.uuid4().hex, lease_seconds=lease_seconds)
    if claim is None:
        return None
    job_id, token = claim['job_id'], claim['lease_token']
    stop = threading.Event()
    lost = threading.Event()

    def heartbeat():
        while not stop.wait(heartbeat_seconds):
            try:
                if not queue.renew(job_id, token, lease_seconds=lease_seconds):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        result = handler(claim)
        if lost.is_set() or not queue.complete(job_id, token, result):
            raise RuntimeError('Worker lost job lease; result not acknowledged')
        return {'job_id': job_id, 'status': 'completed', 'result': result}
    except Exception as exc:
        queue.fail(job_id, token, str(exc), retry_delay=15)
        raise
    finally:
        stop.set()
        thread.join(timeout=max(1, heartbeat_seconds + 1))
