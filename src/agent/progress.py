"""
노드 내부 진행 상황을 SSE 스트림으로 전달하기 위한 thread-local 이벤트 큐.

사용법:
    # 스트리밍 엔드포인트에서:
    q = progress.register(run_id)
    threading.Thread(target=lambda: (progress.set_run_id(run_id), run_graph())).start()

    # 각 노드에서:
    from src.agent.progress import emit
    emit("📡 Naver API 검색 중...")
"""
import queue
import threading

_thread_local = threading.local()
_queues: dict[str, queue.Queue] = {}
_lock = threading.Lock()


def register(run_id: str) -> "queue.Queue[dict]":
    q: queue.Queue = queue.Queue()
    with _lock:
        _queues[run_id] = q
    return q


def set_run_id(run_id: str) -> None:
    _thread_local.run_id = run_id


def emit(message: str) -> None:
    run_id = getattr(_thread_local, "run_id", None)
    if not run_id:
        return
    with _lock:
        q = _queues.get(run_id)
    if q is not None:
        q.put_nowait({"type": "progress", "message": message})


def unregister(run_id: str) -> None:
    with _lock:
        _queues.pop(run_id, None)
