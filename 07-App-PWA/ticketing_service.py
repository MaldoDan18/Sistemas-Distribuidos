# Practica 7 - PWA

import argparse
import json
import socketserver
import threading
import time
import uuid
import random
from pathlib import Path


# --- Nuevo Ticketing Authority: maneja mapa de asientos, reservas, TTL y emisión ---

FILAS = 30
COLUMNAS = 50
TOTAL_ASIENTOS = FILAS * COLUMNAS
RESERVA_TTL_SEGUNDOS = 5.0
SECTION_GAP_ROWS = 2
SECTION_LABEL_ROWS = 1

ZONA_PLATINO = "PLATINO"
ZONA_PREFERENTE = "PREFERENTE"
ZONA_NORMAL = "NORMAL"

TIPO_PLATINO = "platino"
TIPO_PREFERENTE = "preferente"
TIPO_NORMAL = "normal"

ALLOWED_ZONES_BY_TYPE = {
    TIPO_PLATINO: [ZONA_PLATINO, ZONA_PREFERENTE, ZONA_NORMAL],
    TIPO_PREFERENTE: [ZONA_PREFERENTE, ZONA_NORMAL],
    TIPO_NORMAL: [ZONA_NORMAL],
}


def build_zone_seats():
    zones = {
        ZONA_PLATINO: set(),
        ZONA_PREFERENTE: set(),
        ZONA_NORMAL: set(),
    }

    for row in range(FILAS):
        for col in range(COLUMNAS):
            if row <= 2:
                zones[ZONA_PLATINO].add((row, col))
            elif row <= 6:
                zones[ZONA_PREFERENTE].add((row, col))
            else:
                zones[ZONA_NORMAL].add((row, col))

    return zones


class TicketStore:
    def __init__(self, store_file):
        self.store_file = Path(store_file)
        self.lock = threading.Lock()
        self.ticket_count = 0
        self.store_file.parent.mkdir(parents=True, exist_ok=True)

    def create_ticket(self, payload):
        ticket_id = f"TKT-{uuid.uuid4().hex[:12].upper()}"
        created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        seat = payload.get("seat") or {}
        record = {
            "ticket_id": ticket_id,
            "created_at": created_at,
            "sale_id": payload.get("sale_id"),
            "buyer_id": payload.get("buyer_id"),
            "buyer_type": payload.get("buyer_type"),
            "zone": payload.get("zone"),
            "seat": {"row": int(seat.get("row", 0)), "col": int(seat.get("col", 0))},
            "reservation_id": payload.get("reservation_id"),
            "request_id": payload.get("request_id"),
            "server_host": payload.get("server_host"),
            "server_port": payload.get("server_port"),
        }
        line = json.dumps(record, ensure_ascii=False)
        with self.lock:
            with self.store_file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self.ticket_count += 1
            stored_count = self.ticket_count
        return record, stored_count


class TicketState:
    def __init__(self):
        self.meta_lock = threading.Lock()
        self.zone_locks = {
            ZONA_PLATINO: threading.Lock(),
            ZONA_PREFERENTE: threading.Lock(),
            ZONA_NORMAL: threading.Lock(),
        }
        self.zone_free_seats = build_zone_seats()
        self.seat_status = [["FREE" for _ in range(COLUMNAS)] for _ in range(FILAS)]
        self.reservations_by_zone = {ZONA_PLATINO: {}, ZONA_PREFERENTE: {}, ZONA_NORMAL: {}}
        self.reservation_to_zone = {}
        self.sold_count = 0

    def _cleanup_expired_zone_locked(self, zone):
        now = time.monotonic()
        zone_reservations = self.reservations_by_zone[zone]
        expired_ids = [rid for rid, info in zone_reservations.items() if info["expires_at"] <= now]
        for rid in expired_ids:
            info = zone_reservations.pop(rid, None)
            if not info:
                continue
            row, col = info["seat"]
            self.seat_status[row][col] = "FREE"
            self.zone_free_seats[zone].add((row, col))
            with self.meta_lock:
                self.reservation_to_zone.pop(rid, None)

    def request_ticket(self, buyer_id, buyer_type, request_id, specific_row=None, specific_col=None):
        start = time.perf_counter()
        zones = ALLOWED_ZONES_BY_TYPE.get((buyer_type or "").lower(), ALLOWED_ZONES_BY_TYPE[TIPO_NORMAL])

        # specific seat
        if specific_row is not None and specific_col is not None:
            try:
                row = int(specific_row)
                col = int(specific_col)
                if 0 <= row < FILAS and 0 <= col < COLUMNAS:
                    if row <= 2:
                        seat_zone = ZONA_PLATINO
                    elif row <= 6:
                        seat_zone = ZONA_PREFERENTE
                    else:
                        seat_zone = ZONA_NORMAL
                    if seat_zone not in zones:
                        return {"status": "error", "code": "zone_not_allowed", "message": "Tipo de comprador no puede acceder a la zona."}
                    zone_lock = self.zone_locks[seat_zone]
                    if not zone_lock.acquire(timeout=0.05):
                        return {"status": "error", "code": "zone_busy", "message": "Zona ocupada, intenta de nuevo."}
                    try:
                        self._cleanup_expired_zone_locked(seat_zone)
                        if self.seat_status[row][col] == "FREE":
                            reservation_id = str(uuid.uuid4())
                            self.seat_status[row][col] = "RESERVED"
                            self.reservations_by_zone[seat_zone][reservation_id] = {
                                "buyer_id": str(buyer_id),
                                "buyer_type": (buyer_type or TIPO_NORMAL).lower(),
                                "seat": (row, col),
                                "zone": seat_zone,
                                "expires_at": time.monotonic() + RESERVA_TTL_SEGUNDOS,
                                "request_id": request_id,
                            }
                            with self.meta_lock:
                                self.reservation_to_zone[reservation_id] = seat_zone
                            return {"status": "ok", "reservation_id": reservation_id, "zone": seat_zone, "seat": {"row": row, "col": col}, "ttl_seconds": RESERVA_TTL_SEGUNDOS}
                        else:
                            return {"status": "error", "code": "seat_not_available", "message": "Asiento no disponible."}
                    finally:
                        zone_lock.release()
            except (ValueError, TypeError):
                pass

        # random allocation
        for zone in zones:
            zone_lock = self.zone_locks[zone]
            if not zone_lock.acquire(timeout=0.02):
                continue
            try:
                self._cleanup_expired_zone_locked(zone)
                if not self.zone_free_seats[zone]:
                    continue
                seat = random.choice(tuple(self.zone_free_seats[zone]))
                row, col = seat
                reservation_id = str(uuid.uuid4())
                self.zone_free_seats[zone].remove(seat)
                self.seat_status[row][col] = "RESERVED"
                self.reservations_by_zone[zone][reservation_id] = {
                    "buyer_id": str(buyer_id),
                    "buyer_type": (buyer_type or TIPO_NORMAL).lower(),
                    "seat": seat,
                    "zone": zone,
                    "expires_at": time.monotonic() + RESERVA_TTL_SEGUNDOS,
                    "request_id": request_id,
                }
                with self.meta_lock:
                    self.reservation_to_zone[reservation_id] = zone
                return {"status": "ok", "reservation_id": reservation_id, "zone": zone, "seat": {"row": row, "col": col}, "ttl_seconds": RESERVA_TTL_SEGUNDOS}
            finally:
                zone_lock.release()

        return {"status": "error", "code": "no_zone_available", "message": "No hay asientos disponibles para el tipo de comprador en este momento."}

    def purchase(self, buyer_id, reservation_id, request_id, sale_id=None, server_host=None, server_port=None):
        if not reservation_id:
            return {"status": "error", "code": "missing_reservation_id"}
        with self.meta_lock:
            zone = self.reservation_to_zone.get(reservation_id)
        if zone is None:
            return {"status": "error", "code": "invalid_or_expired_reservation"}
        zone_lock = self.zone_locks[zone]
        if not zone_lock.acquire(timeout=0.05):
            return {"status": "error", "code": "zone_busy_retry"}
        try:
            self._cleanup_expired_zone_locked(zone)
            info = self.reservations_by_zone[zone].get(reservation_id)
            if info is None:
                return {"status": "error", "code": "invalid_or_expired_reservation"}
            if info["buyer_id"] != str(buyer_id):
                return {"status": "error", "code": "reservation_owner_mismatch"}

            row, col = info["seat"]
            # create ticket record
            ticket_payload = {
                "sale_id": sale_id,
                "buyer_id": str(buyer_id),
                "buyer_type": info.get("buyer_type"),
                "zone": zone,
                "seat": {"row": row, "col": col},
                "reservation_id": reservation_id,
                "request_id": request_id,
                "server_host": server_host,
                "server_port": server_port,
            }
            try:
                ticket, stored_count = self.server.ticket_store.create_ticket(ticket_payload)
            except Exception as exc:
                return {"status": "error", "code": "ticket_generation_failed", "message": str(exc)}

            # mark sold
            self.reservations_by_zone[zone].pop(reservation_id, None)
            with self.meta_lock:
                self.reservation_to_zone.pop(reservation_id, None)
                self.seat_status[row][col] = "SOLD"
                self.sold_count += 1
            return {"status": "ok", "reservation_id": reservation_id, "zone": zone, "seat": {"row": row, "col": col}, "ticket_id": ticket["ticket_id"], "ticket": ticket, "stored_count": stored_count, "sold_count": self.sold_count}
        finally:
            zone_lock.release()

    def get_snapshot(self):
        lock_order = [self.zone_locks[ZONA_PLATINO], self.zone_locks[ZONA_PREFERENTE], self.zone_locks[ZONA_NORMAL]]
        for lock in lock_order:
            lock.acquire()
        try:
            seat_status_copy = [row[:] for row in self.seat_status]
            reserved_count = sum(len(self.reservations_by_zone[z]) for z in self.reservations_by_zone)
            with self.meta_lock:
                return {"sold_count": self.sold_count, "reserved_count": reserved_count, "free_count": TOTAL_ASIENTOS - self.sold_count - reserved_count, "seat_status": seat_status_copy}
        finally:
            for lock in reversed(lock_order):
                lock.release()


class TicketingServiceHandler(socketserver.StreamRequestHandler):
    def send_json(self, payload):
        try:
            self.wfile.write((json.dumps(payload) + "\n").encode("utf-8"))
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return False

    def handle(self):
        while True:
            try:
                raw_line = self.rfile.readline()
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                return
            if not raw_line:
                return
            try:
                payload = json.loads(raw_line.decode("utf-8").strip())
            except json.JSONDecodeError:
                self.send_json({"type": "ERROR", "code": "invalid_json"})
                continue

            message_type = (payload.get("type") or "").upper()
            request_id = payload.get("request_id", str(uuid.uuid4()))

            if message_type == "REQUEST_TICKET":
                buyer_id = payload.get("buyer_id")
                buyer_type = payload.get("buyer_type", TIPO_NORMAL)
                row = payload.get("row")
                col = payload.get("col")
                resp = self.server.ticket_state.request_ticket(buyer_id, buyer_type, request_id, row, col)
                resp["type"] = "REQUEST_TICKET_RESPONSE"
                self.send_json(resp)
                continue

            if message_type == "PURCHASE":
                buyer_id = payload.get("buyer_id")
                reservation_id = payload.get("reservation_id")
                sale_id = payload.get("sale_id")
                server_host = payload.get("server_host")
                server_port = payload.get("server_port")
                resp = self.server.ticket_state.purchase(buyer_id, reservation_id, request_id, sale_id, server_host, server_port)
                resp["type"] = "PURCHASE_RESPONSE"
                self.send_json(resp)
                continue

            if message_type == "AVAILABILITY":
                snap = self.server.ticket_state.get_snapshot()
                resp = {"type": "AVAILABILITY_RESPONSE", "status": "ok", "seat_status": snap.get("seat_status"), "sold_count": snap.get("sold_count"), "reserved_count": snap.get("reserved_count"), "free_count": snap.get("free_count")}
                self.send_json(resp)
                continue

            self.send_json({"type": "ERROR", "code": "unknown_message_type"})


class TicketingServiceServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, server_address, handler_class, ticket_state, ticket_store):
        super().__init__(server_address, handler_class)
        self.ticket_state = ticket_state
        self.ticket_store = ticket_store


def parse_args():
    parser = argparse.ArgumentParser(description="Ticketing Service (authority) para práctica 08")
    parser.add_argument("--host", default="127.0.0.1", help="Host para escuchar conexiones")
    parser.add_argument("--port", type=int, default=7000, help="Puerto para escuchar conexiones")
    parser.add_argument("--store-file", default="tickets/tickets.txt", help="Archivo de almacenamiento de tickets")
    return parser.parse_args()


def main():
    args = parse_args()
    ticket_store = TicketStore(args.store_file)
    ticket_state = TicketState()
    server = TicketingServiceServer((args.host, args.port), TicketingServiceHandler, ticket_state, ticket_store)

    # allow handler access to server internals
    server.ticket_state.server = server

    print("Ticketing Authority iniciado")
    print(f"Escuchando en {args.host}:{args.port}")
    print(f"Archivo de tickets: {ticket_store.store_file}")

    try:
        # Start background cleanup thread to free expired reservations
        def cleanup_loop():
            while True:
                try:
                    for zone in (ZONA_PLATINO, ZONA_PREFERENTE, ZONA_NORMAL):
                        ticket_state._cleanup_expired_zone_locked(zone)
                except Exception:
                    pass
                time.sleep(1.0)

        cleanup_t = threading.Thread(target=cleanup_loop, daemon=True)
        cleanup_t.start()

        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Ticketing] Interrupción recibida. Cerrando servicio...")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
