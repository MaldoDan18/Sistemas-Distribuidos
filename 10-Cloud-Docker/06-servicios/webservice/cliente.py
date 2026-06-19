# Cliente web para la practica 6

from __future__ import annotations

import argparse
import json
import random
import threading
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SOCKET_TIMEOUT = 20.0

TIPO_PLATINO = "platino"
TIPO_PREFERENTE = "preferente"
TIPO_NORMAL = "normal"

TYPE_ALIAS = {
    "a": TIPO_PLATINO,
    "b": TIPO_NORMAL,
    "c": TIPO_PREFERENTE,
    TIPO_PLATINO: TIPO_PLATINO,
    TIPO_PREFERENTE: TIPO_PREFERENTE,
    TIPO_NORMAL: TIPO_NORMAL,
}

stats_lock = threading.Lock()
terminal_lock = threading.Lock()
sold_out_event = threading.Event()
threads: list[threading.Thread] = []

metrics = {
    "buyers_success": 0,
    "buyers_fail": 0,
    "reserve_time_total": 0.0,
    "purchase_time_total": 0.0,
    "reserve_count": 0,
    "purchase_count": 0,
    "network_errors": 0,
}

sales_start_ts: float | None = None
sales_end_ts: float | None = None


def http_json_request(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = SOCKET_TIMEOUT) -> dict[str, Any]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = Request(url, data=body, headers=headers, method=method.upper())

    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
            return json.loads(raw_body) if raw_body else {}
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8") if exc.fp else ""
        try:
            error_payload = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            error_payload = {"message": raw_body}
        raise RuntimeError(error_payload.get("message") or f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise ConnectionError(f"No fue posible conectar con {url}: {exc.reason}") from exc


def avg(total: float, count: int) -> float:
    if count == 0:
        return 0.0
    return total / count


def normalize_client_type(raw_type: str) -> str:
    normalized = TYPE_ALIAS.get((raw_type or "").strip().lower())
    if normalized is None:
        raise ValueError("Tipo inválido. Usa A/B/C o normal/preferente/platino")
    return normalized


def notify_coordinator(coordinator_url: str | None, path: str, payload: dict[str, Any]) -> None:
    if not coordinator_url:
        return
    try:
        http_json_request("POST", f"{coordinator_url.rstrip('/')}{path}", payload)
    except Exception:
        with stats_lock:
            metrics["network_errors"] += 1


def monitor_server_health(server_url: str) -> None:
    while not sold_out_event.is_set():
        try:
            response = http_json_request("GET", f"{server_url}/health")
            if response.get("status") == "closed":
                sold_out_event.set()
                return

            sold_count = int(response.get("sold_count") or 0)
            sold_limit = int(response.get("sold_limit") or 0)
            if sold_limit > 0 and sold_count >= sold_limit:
                sold_out_event.set()
                return
        except Exception:
            pass

        time.sleep(0.35)


def register_and_wait_start(server_url: str, client_id: str, client_type: str, buyers_count: int) -> None:
    register_response = http_json_request(
        "POST",
        f"{server_url}/register",
        {
            "client_id": client_id,
            "client_type": client_type,
            "buyers": buyers_count,
            "request_id": str(uuid.uuid4()),
        },
    )

    if register_response.get("status") != "ok":
        raise RuntimeError(f"Registro rechazado: {register_response}")

    with terminal_lock:
        print(
            f"Registrado como {client_id}. "
            f"Conectados: {register_response.get('connected_clients')}/{register_response.get('expected_clients')}"
        )

    ready_response = http_json_request(
        "POST",
        f"{server_url}/ready",
        {
            "client_id": client_id,
            "request_id": str(uuid.uuid4()),
        },
    )
    if ready_response.get("status") != "ok":
        raise RuntimeError(f"READY rechazado: {ready_response}")

    with terminal_lock:
        print("Esperando señal START del servidor...")

    while not sold_out_event.is_set():
        start_response = http_json_request("GET", f"{server_url}/start")
        if start_response.get("started"):
            with terminal_lock:
                print(
                    f"START recibido. "
                    f"Clientes listos: {start_response.get('ready_clients')}/{start_response.get('expected_clients')}"
                )
            return
        time.sleep(0.2)


def buyer_worker(buyer_number: int, server_url: str, client_id: str, client_type: str) -> None:
    buyer_id = f"{client_id}-B{buyer_number}"
    buyer_started = time.perf_counter()
    purchased = False
    local_reserve_time = 0.0
    local_purchase_time = 0.0
    retry_delay = 0.0

    while not sold_out_event.is_set():
        if retry_delay > 0:
            time.sleep(retry_delay)
            retry_delay = 0.0
        time.sleep(random.uniform(0.01, 0.06))

        reserve_payload = {
            "buyer_id": buyer_id,
            "buyer_type": client_type,
        }

        reserve_started = time.perf_counter()
        try:
            reserve_response = http_json_request("POST", f"{server_url}/reserve", reserve_payload)
        except Exception:
            with stats_lock:
                metrics["network_errors"] += 1
            retry_delay = min(1.0, 0.1 if retry_delay == 0.0 else retry_delay * 1.3)
            continue

        reserve_elapsed = time.perf_counter() - reserve_started
        local_reserve_time += reserve_elapsed

        with stats_lock:
            metrics["reserve_count"] += 1
            metrics["reserve_time_total"] += reserve_elapsed

        if reserve_response.get("status") != "ok":
            error_code = reserve_response.get("code")
            reserve_status = reserve_response.get("status")
            if reserve_status in {"closed", "sold_out"}:
                sold_out_event.set()
                break
            if reserve_status == "not_started":
                time.sleep(0.15)
                continue
            if reserve_status == "error" and error_code == "no_zone_available":
                time.sleep(0.05)
                continue
            if error_code in {"sales_closed", "sold_limit_reached", "sold_out"}:
                break
            retry_delay = min(1.0, 0.1 if retry_delay == 0.0 else retry_delay * 1.3)
            continue

        reservation = reserve_response.get("reservation") or {}
        reservation_id = reservation.get("reservation_id")
        if not reservation_id:
            continue

        purchase_payload = {
            "buyer_id": buyer_id,
            "reservation_id": reservation_id,
        }

        purchase_started = time.perf_counter()
        try:
            purchase_response = http_json_request("POST", f"{server_url}/purchase", purchase_payload)
        except Exception:
            with stats_lock:
                metrics["network_errors"] += 1
            retry_delay = min(1.0, 0.1 if retry_delay == 0.0 else retry_delay * 1.3)
            continue

        purchase_elapsed = time.perf_counter() - purchase_started
        local_purchase_time += purchase_elapsed

        with stats_lock:
            metrics["purchase_count"] += 1
            metrics["purchase_time_total"] += purchase_elapsed

        if purchase_response.get("status") == "ok":
            purchased = True
            if (purchase_response.get("remaining") or 1) <= 0:
                sold_out_event.set()
            break

        error_code = purchase_response.get("code")
        purchase_status = purchase_response.get("status")
        if purchase_status in {"closed", "sold_out"}:
            sold_out_event.set()
            break
        if purchase_status == "not_started":
            time.sleep(0.15)
            continue
        if error_code in {"sales_closed", "sold_limit_reached", "sold_out"}:
            break
        retry_delay = min(1.0, 0.1 if retry_delay == 0.0 else retry_delay * 1.3)

    buyer_total_elapsed = time.perf_counter() - buyer_started

    with stats_lock:
        if purchased:
            metrics["buyers_success"] += 1
        else:
            metrics["buyers_fail"] += 1

    with terminal_lock:
        status = "compra exitosa" if purchased else "sin compra"
        print(f"[{buyer_id}] {status} en {buyer_total_elapsed:.3f} s")


def print_summary(client_id: str, client_type: str, buyers_count: int) -> None:
    success = metrics["buyers_success"]
    fail = metrics["buyers_fail"]
    total_time = 0.0
    if sales_start_ts is not None and sales_end_ts is not None:
        total_time = sales_end_ts - sales_start_ts

    with terminal_lock:
        print("\n========== Resumen del Cliente Web ==========")
        print(f"Cliente: {client_id}")
        print(f"Tipo de compradores: {client_type}")
        print(f"Compradores creados: {buyers_count}")
        print(f"Compradores con compra: {success}")
        print(f"Compradores sin compra: {fail}")
        print(f"Tiempo total local: {total_time:.4f} s")
        print(f"Promedio reserva: {avg(metrics['reserve_time_total'], metrics['reserve_count']):.6f} s")
        print(f"Promedio compra: {avg(metrics['purchase_time_total'], metrics['purchase_count']):.6f} s")
        print(f"Errores de red detectados: {metrics['network_errors']}")
        print("===========================================\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cliente web para la practica 6")
    parser.add_argument("client_type", help="Tipo de cliente: A/B/C o normal/preferente/platino")
    parser.add_argument("buyers", type=int, help="Cantidad de compradores (hilos) para este cliente")
    parser.add_argument("--server-url", default="http://127.0.0.1:8080", help="URL base del servidor web")
    parser.add_argument("--client-id", default=None, help="Identificador unico del cliente")
    parser.add_argument("--sale-id", default="venta-web", help="Identificador de venta para coordinador")
    parser.add_argument("--coordinator-url", default=None, help="URL base del coordinador web")
    parser.add_argument("--wait-coordinator", action="store_true", help="Espera el coordinador antes de arrancar")
    parser.add_argument("--wait-timeout", type=float, default=10.0, help="Tiempo maximo de espera al coordinador")
    return parser.parse_args()


def wait_for_coordinator(coordinator_url: str, timeout: float) -> None:
    started = time.perf_counter()
    health_url = f"{coordinator_url.rstrip('/')}/health"
    while True:
        try:
            http_json_request("GET", health_url)
            return
        except Exception:
            if time.perf_counter() - started >= timeout:
                raise TimeoutError("No fue posible conectar con el coordinador")
            time.sleep(0.25)


def main() -> None:
    global sales_start_ts, sales_end_ts

    args = parse_args()
    normalized_type = normalize_client_type(args.client_type)

    if args.buyers <= 0:
        raise ValueError("buyers debe ser mayor que 0")

    client_id = args.client_id or f"{args.client_type.upper()}-{str(uuid.uuid4())[:6]}"

    with terminal_lock:
        print("Cliente web iniciado")
        print(f"ID cliente: {client_id}")
        print(f"Servidor objetivo: {args.server_url}")
        print(f"Tipo de compradores: {normalized_type}")
        print(f"Compradores a crear: {args.buyers}")

    if args.coordinator_url:
        notify_coordinator(
            args.coordinator_url,
            "/clients/connect",
            {
                "sale_id": args.sale_id,
                "client_id": client_id,
                "buyers": args.buyers,
            },
        )
        if args.wait_coordinator:
            wait_for_coordinator(args.coordinator_url, args.wait_timeout)

    register_and_wait_start(args.server_url, client_id, normalized_type, args.buyers)

    health_thread = threading.Thread(target=monitor_server_health, args=(args.server_url,), daemon=True)
    health_thread.start()

    sales_start_ts = time.perf_counter()

    for buyer_number in range(1, args.buyers + 1):
        thread = threading.Thread(
            target=buyer_worker,
            args=(buyer_number, args.server_url, client_id, normalized_type),
            daemon=False,
        )
        threads.append(thread)
        thread.start()
        time.sleep(0.001)

    for thread in threads:
        thread.join()

    sales_end_ts = time.perf_counter()

    if args.coordinator_url:
        notify_coordinator(
            args.coordinator_url,
            "/clients/done",
            {
                "sale_id": args.sale_id,
                "client_id": client_id,
            },
        )

    print_summary(client_id, normalized_type, args.buyers)


if __name__ == "__main__":
    main()
