import argparse
import json
import random
import socket
import threading
import time
import uuid

FILAS = 25
COLUMNAS = 40
TOTAL_ASIENTOS = FILAS * COLUMNAS
COMPRADORES_POR_ASIENTO = 2
TOTAL_COMPRADORES = TOTAL_ASIENTOS * COMPRADORES_POR_ASIENTO

SOCKET_TIMEOUT = 3.0


stats_lock = threading.Lock()
terminal_lock = threading.Lock()
sold_out_event = threading.Event()
threads = []

metrics = {
    "buyers_success": 0,
    "buyers_fail": 0,
    "buyer_total_success": 0.0,
    "buyer_search_success": 0.0,
    "buyer_purchase_success": 0.0,
    "buyer_wait_success": 0.0,
    "buyer_total_fail": 0.0,
    "buyer_wait_fail": 0.0,
    "request_time_total": 0.0,
    "purchase_time_total": 0.0,
    "request_count": 0,
    "purchase_count": 0,
    "attempts_success": 0,
    "attempts_fail": 0,
    "network_errors": 0,
}

sales_start_ts = None
sales_end_ts = None


def avg(total, count):
    if count == 0:
        return 0.0
    return total / count


def send_request(host, port, payload):
    data = (json.dumps(payload) + "\n").encode("utf-8")
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT) as sock:
        sock.settimeout(SOCKET_TIMEOUT)
        sock.sendall(data)
        response_bytes = b""
        while not response_bytes.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_bytes += chunk

    if not response_bytes:
        raise ConnectionError("Respuesta vacía del servidor")

    return json.loads(response_bytes.decode("utf-8").strip())


def buyer_worker(buyer_id, host, port):
    buyer_started = time.perf_counter()
    wait_random_accum = 0.0
    request_time_accum = 0.0
    purchase_time_accum = 0.0
    attempts = 0
    purchased = False

    while not sold_out_event.is_set():
        pause = random.uniform(0.1, 2.0)
        time.sleep(pause)
        wait_random_accum += pause

        request_payload = {
            "action": "request_ticket",
            "buyer_id": buyer_id,
            "request_id": str(uuid.uuid4()),
        }

        attempts += 1
        request_started = time.perf_counter()
        try:
            request_response = send_request(host, port, request_payload)
        except Exception:
            with stats_lock:
                metrics["network_errors"] += 1
            continue

        request_elapsed = time.perf_counter() - request_started
        request_time_accum += request_elapsed

        with stats_lock:
            metrics["request_count"] += 1
            metrics["request_time_total"] += request_elapsed

        request_status = request_response.get("status")
        if request_status == "not_started":
            time.sleep(0.2)
            continue
        if request_status == "sold_out":
            sold_out_event.set()
            break
        if request_status != "ok":
            continue

        reservation_id = request_response.get("reservation_id")
        if not reservation_id:
            continue

        purchase_payload = {
            "action": "purchase",
            "buyer_id": buyer_id,
            "reservation_id": reservation_id,
            "request_id": str(uuid.uuid4()),
        }

        purchase_started = time.perf_counter()
        try:
            purchase_response = send_request(host, port, purchase_payload)
        except Exception:
            with stats_lock:
                metrics["network_errors"] += 1
            continue

        purchase_elapsed = time.perf_counter() - purchase_started
        purchase_time_accum += purchase_elapsed

        with stats_lock:
            metrics["purchase_count"] += 1
            metrics["purchase_time_total"] += purchase_elapsed

        purchase_status = purchase_response.get("status")
        if purchase_status == "not_started":
            time.sleep(0.2)
            continue
        if purchase_status == "sold_out":
            sold_out_event.set()
            break
        if purchase_status == "ok":
            purchased = True
            sold_count = purchase_response.get("sold_count", 0)
            if sold_count >= TOTAL_ASIENTOS:
                sold_out_event.set()
            break

    buyer_total_elapsed = time.perf_counter() - buyer_started
    buyer_search_elapsed = wait_random_accum + request_time_accum

    with stats_lock:
        if purchased:
            metrics["buyers_success"] += 1
            metrics["buyer_total_success"] += buyer_total_elapsed
            metrics["buyer_search_success"] += buyer_search_elapsed
            metrics["buyer_purchase_success"] += purchase_time_accum
            metrics["buyer_wait_success"] += wait_random_accum
            metrics["attempts_success"] += attempts
        else:
            metrics["buyers_fail"] += 1
            metrics["buyer_total_fail"] += buyer_total_elapsed
            metrics["buyer_wait_fail"] += wait_random_accum
            metrics["attempts_fail"] += attempts


def print_summary():
    success = metrics["buyers_success"]
    fail = metrics["buyers_fail"]

    with terminal_lock:
        print("\n========== Resumen de Tiempos del Cliente ==========")
        print(f"Compradores creados: {TOTAL_COMPRADORES}")
        print(f"Compradores con compra: {success}")
        print(f"Compradores sin compra: {fail}")
        print(f"Tiempo total general: {sales_end_ts - sales_start_ts:.4f} s")
        print(
            f"Promedio total por comprador exitoso: "
            f"{avg(metrics['buyer_total_success'], success):.4f} s"
        )
        print(
            f"Promedio de búsqueda por comprador exitoso: "
            f"{avg(metrics['buyer_search_success'], success):.4f} s"
        )
        print(
            f"Promedio de compra por comprador exitoso: "
            f"{avg(metrics['buyer_purchase_success'], success):.6f} s"
        )
        print(
            f"Promedio de espera aleatoria por comprador exitoso: "
            f"{avg(metrics['buyer_wait_success'], success):.4f} s"
        )
        print(
            f"Promedio total por comprador sin compra: "
            f"{avg(metrics['buyer_total_fail'], fail):.4f} s"
        )
        print(
            f"Promedio de espera aleatoria por comprador sin compra: "
            f"{avg(metrics['buyer_wait_fail'], fail):.4f} s"
        )
        print(
            f"Promedio de intentos por comprador exitoso: "
            f"{avg(metrics['attempts_success'], success):.2f}"
        )
        print(
            f"Promedio de intentos por comprador sin compra: "
            f"{avg(metrics['attempts_fail'], fail):.2f}"
        )
        print(
            f"Tiempo promedio request_ticket (red + servidor): "
            f"{avg(metrics['request_time_total'], metrics['request_count']):.6f} s"
        )
        print(
            f"Tiempo promedio purchase (red + servidor): "
            f"{avg(metrics['purchase_time_total'], metrics['purchase_count']):.6f} s"
        )
        print(f"Errores de red detectados: {metrics['network_errors']}")
        print("====================================================\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Cliente de boletos - Práctica 2 Fase 1")
    parser.add_argument("--host", default="127.0.0.1", help="Host del servidor")
    parser.add_argument("--port", type=int, default=5000, help="Puerto del servidor")
    return parser.parse_args()


def wait_for_sales_start(host, port):
    with terminal_lock:
        print("Esperando señal de inicio del servidor...")

    while True:
        try:
            response = send_request(host, port, {"action": "health", "request_id": str(uuid.uuid4())})
        except Exception:
            with stats_lock:
                metrics["network_errors"] += 1
            time.sleep(0.4)
            continue

        if response.get("status") == "ok" and response.get("sales_open"):
            with terminal_lock:
                print("Servidor confirmó inicio de venta.")
            return

        time.sleep(0.3)


def main():
    global sales_start_ts, sales_end_ts

    args = parse_args()

    with terminal_lock:
        print("Cliente de compra iniciado")
        print(f"Servidor destino: {args.host}:{args.port}")
        print(f"Asientos esperados: {TOTAL_ASIENTOS}")
        print(f"Compradores a crear: {TOTAL_COMPRADORES}")

    wait_for_sales_start(args.host, args.port)

    sales_start_ts = time.perf_counter()

    for buyer_id in range(1, TOTAL_COMPRADORES + 1):
        thread = threading.Thread(target=buyer_worker, args=(buyer_id, args.host, args.port), daemon=False)
        threads.append(thread)
        thread.start()
        time.sleep(0.0005)

    for thread in threads:
        thread.join()

    sales_end_ts = time.perf_counter()
    print_summary()


if __name__ == "__main__":
    main()
