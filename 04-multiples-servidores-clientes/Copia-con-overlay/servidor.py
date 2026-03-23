import argparse
import json
import random
import socketserver
import threading
import time
import tkinter as tk
import uuid

FILAS = 30
COLUMNAS = 50
TOTAL_ASIENTOS = FILAS * COLUMNAS
RESERVA_TTL_SEGUNDOS = 1.0
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


class TicketState:
    def __init__(self):
        self.meta_lock = threading.Lock()
        self.terminal_lock = threading.Lock()

        self.zone_locks = {
            ZONA_PLATINO: threading.Lock(),
            ZONA_PREFERENTE: threading.Lock(),
            ZONA_NORMAL: threading.Lock(),
        }

        self.zone_free_seats = build_zone_seats()
        self.seat_status = [["FREE" for _ in range(COLUMNAS)] for _ in range(FILAS)]

        self.reservations_by_zone = {
            ZONA_PLATINO: {},
            ZONA_PREFERENTE: {},
            ZONA_NORMAL: {},
        }
        self.reservation_to_zone = {}

        self.unique_buyers = set()
        self.registered_buyers_by_type = {
            TIPO_PLATINO: 0,
            TIPO_PREFERENTE: 0,
            TIPO_NORMAL: 0,
        }
        self.purchased_by_type = {
            TIPO_PLATINO: 0,
            TIPO_PREFERENTE: 0,
            TIPO_NORMAL: 0,
        }
        self.sold_count = 0
        self.sales_started_at = None
        self.sales_finished_at = None
        self.sales_open_event = threading.Event()
        self.sales_closed_event = threading.Event()
        self.sold_out_event = threading.Event()
        self.summary_printed = False
        self.hitos_reportados = set()
        self.close_reason = None

        self.metrics = {
            "request_ticket_count": 0,
            "purchase_count": 0,
            "request_ticket_time_total": 0.0,
            "purchase_time_total": 0.0,
            "request_ticket_ok": 0,
            "purchase_ok": 0,
            "purchase_rejected": 0,
            "expired_releases": 0,
            "not_started_count": 0,
        }

    def open_sales(self):
        with self.meta_lock:
            if self.sales_open_event.is_set():
                return
            self.sales_started_at = time.perf_counter()
            self.sales_open_event.set()

        with self.terminal_lock:
            print("Actualizaciones de venta:")

    def sales_open(self):
        return self.sales_open_event.is_set()

    def sales_closed(self):
        return self.sales_closed_event.is_set()

    def close_sales(self, reason):
        lock_order = [self.zone_locks[ZONA_PLATINO], self.zone_locks[ZONA_PREFERENTE], self.zone_locks[ZONA_NORMAL]]
        for lock in lock_order:
            lock.acquire()

        try:
            with self.meta_lock:
                if self.sales_closed_event.is_set():
                    return

            released = 0
            for zone in (ZONA_PLATINO, ZONA_PREFERENTE, ZONA_NORMAL):
                zone_reservations = self.reservations_by_zone[zone]
                for reservation_id, info in list(zone_reservations.items()):
                    row, col = info["seat"]
                    self.seat_status[row][col] = "FREE"
                    self.zone_free_seats[zone].add((row, col))
                    zone_reservations.pop(reservation_id, None)
                    released += 1

            with self.meta_lock:
                self.reservation_to_zone.clear()
                if self.sales_finished_at is None:
                    self.sales_finished_at = time.perf_counter()
                self.close_reason = reason
                self.sales_closed_event.set()
                self.sold_out_event.set()

            with self.terminal_lock:
                if released > 0:
                    print(f"Actualización: cierre de venta liberó {released} reservas activas.")
        finally:
            for lock in reversed(lock_order):
                lock.release()

    def register_buyer(self, buyer_id):
        if not buyer_id:
            return
        with self.meta_lock:
            self.unique_buyers.add(str(buyer_id))

    def register_client_buyers(self, client_type, buyers_count):
        normalized = (client_type or "").lower()
        if normalized not in self.registered_buyers_by_type:
            normalized = TIPO_NORMAL
        with self.meta_lock:
            self.registered_buyers_by_type[normalized] += max(0, int(buyers_count))

    def _remaining_buyers_locked(self, buyer_type):
        return max(
            0,
            self.registered_buyers_by_type[buyer_type] - self.purchased_by_type[buyer_type],
        )

    def _eligible_remaining_for_zone_locked(self, zone):
        remaining_platino = self._remaining_buyers_locked(TIPO_PLATINO)
        remaining_preferente = self._remaining_buyers_locked(TIPO_PREFERENTE)
        remaining_normal = self._remaining_buyers_locked(TIPO_NORMAL)

        if zone == ZONA_PLATINO:
            return remaining_platino
        if zone == ZONA_PREFERENTE:
            return remaining_platino + remaining_preferente
        return remaining_platino + remaining_preferente + remaining_normal

    def _is_sale_still_possible_locked(self):
        for zone in (ZONA_PLATINO, ZONA_PREFERENTE, ZONA_NORMAL):
            available_or_reserved = len(self.zone_free_seats[zone]) + len(self.reservations_by_zone[zone])
            if available_or_reserved <= 0:
                continue
            if self._eligible_remaining_for_zone_locked(zone) > 0:
                return True
        return False

    def _close_if_unsellable_locked(self):
        if self.sales_closed_event.is_set() or not self.sales_open_event.is_set():
            return False
        if self.sold_count >= TOTAL_ASIENTOS:
            return False
        if self._is_sale_still_possible_locked():
            return False

        if self.sales_finished_at is None:
            self.sales_finished_at = time.perf_counter()
        self.close_reason = "unsellable_remaining"
        self.sales_closed_event.set()
        self.sold_out_event.set()
        return True

    def _cleanup_expired_zone_locked(self, zone):
        now = time.monotonic()
        zone_reservations = self.reservations_by_zone[zone]
        expired_ids = [
            reservation_id
            for reservation_id, info in zone_reservations.items()
            if info["expires_at"] <= now
        ]

        for reservation_id in expired_ids:
            info = zone_reservations.pop(reservation_id)
            row, col = info["seat"]
            self.seat_status[row][col] = "FREE"
            self.zone_free_seats[zone].add((row, col))
            with self.meta_lock:
                self.reservation_to_zone.pop(reservation_id, None)
                self.metrics["expired_releases"] += 1

    def _report_progress_milestones_locked(self):
        for porcentaje, umbral in (
            (25, int(TOTAL_ASIENTOS * 0.25)),
            (50, int(TOTAL_ASIENTOS * 0.50)),
            (75, int(TOTAL_ASIENTOS * 0.75)),
            (100, TOTAL_ASIENTOS),
        ):
            if self.sold_count >= umbral and porcentaje not in self.hitos_reportados:
                self.hitos_reportados.add(porcentaje)
                with self.terminal_lock:
                    print(f"Actualización: {porcentaje}% de boletos vendidos ({self.sold_count}/{TOTAL_ASIENTOS}).")

    def request_ticket(self, buyer_id, buyer_type, request_id):
        started = time.perf_counter()

        if self.sales_closed_event.is_set():
            return {"status": "closed", "message": "La venta fue cerrada."}

        if not self.sales_open_event.is_set():
            with self.meta_lock:
                self.metrics["not_started_count"] += 1
                self.metrics["request_ticket_time_total"] += time.perf_counter() - started
            return {"status": "not_started", "message": "La venta aún no inicia."}

        self.register_buyer(buyer_id)
        zones = ALLOWED_ZONES_BY_TYPE.get((buyer_type or "").lower(), ALLOWED_ZONES_BY_TYPE[TIPO_NORMAL])

        with self.meta_lock:
            self.metrics["request_ticket_count"] += 1

        for zone in zones:
            zone_lock = self.zone_locks[zone]
            acquired = zone_lock.acquire(timeout=0.02)
            if not acquired:
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
                    self.metrics["request_ticket_ok"] += 1
                    self.metrics["request_ticket_time_total"] += time.perf_counter() - started

                return {
                    "status": "ok",
                    "reservation_id": reservation_id,
                    "zone": zone,
                    "seat": {"row": row, "col": col},
                    "ttl_seconds": RESERVA_TTL_SEGUNDOS,
                }
            finally:
                zone_lock.release()

        close_now = False
        lock_order = [self.zone_locks[ZONA_PLATINO], self.zone_locks[ZONA_PREFERENTE], self.zone_locks[ZONA_NORMAL]]
        for lock in lock_order:
            lock.acquire()
        try:
            with self.meta_lock:
                close_now = self._close_if_unsellable_locked()
        finally:
            for lock in reversed(lock_order):
                lock.release()

        if close_now:
            with self.terminal_lock:
                print("Actualización: no hay compradores elegibles para los asientos restantes. Cerrando venta.")
            return {"status": "closed", "message": "La venta fue cerrada por falta de demanda elegible."}

        with self.meta_lock:
            self.metrics["request_ticket_time_total"] += time.perf_counter() - started
            sold_count = self.sold_count

        if sold_count >= TOTAL_ASIENTOS:
            return {"status": "sold_out", "message": "No hay asientos disponibles."}

        return {
            "status": "error",
            "code": "no_zone_available",
            "message": "No hay asientos disponibles para el tipo de comprador en este momento.",
        }

    def purchase(self, buyer_id, reservation_id, request_id):
        started = time.perf_counter()

        if self.sales_closed_event.is_set():
            return {"status": "closed", "message": "La venta fue cerrada."}

        if not self.sales_open_event.is_set():
            with self.meta_lock:
                self.metrics["not_started_count"] += 1
                self.metrics["purchase_time_total"] += time.perf_counter() - started
            return {"status": "not_started", "message": "La venta aún no inicia."}

        if not reservation_id:
            return {"status": "error", "code": "missing_reservation_id"}

        with self.meta_lock:
            self.metrics["purchase_count"] += 1
            zone = self.reservation_to_zone.get(reservation_id)

        if zone is None:
            with self.meta_lock:
                self.metrics["purchase_rejected"] += 1
                self.metrics["purchase_time_total"] += time.perf_counter() - started
            return {"status": "error", "code": "invalid_or_expired_reservation"}

        zone_lock = self.zone_locks[zone]
        acquired = zone_lock.acquire(timeout=0.05)
        if not acquired:
            with self.meta_lock:
                self.metrics["purchase_rejected"] += 1
                self.metrics["purchase_time_total"] += time.perf_counter() - started
            return {"status": "error", "code": "zone_busy_retry"}

        try:
            self._cleanup_expired_zone_locked(zone)
            info = self.reservations_by_zone[zone].get(reservation_id)
            if info is None:
                with self.meta_lock:
                    self.metrics["purchase_rejected"] += 1
                    self.metrics["purchase_time_total"] += time.perf_counter() - started
                return {"status": "error", "code": "invalid_or_expired_reservation"}

            if info["buyer_id"] != str(buyer_id):
                with self.meta_lock:
                    self.metrics["purchase_rejected"] += 1
                    self.metrics["purchase_time_total"] += time.perf_counter() - started
                return {"status": "error", "code": "reservation_owner_mismatch"}

            self.reservations_by_zone[zone].pop(reservation_id, None)
            with self.meta_lock:
                self.reservation_to_zone.pop(reservation_id, None)

            row, col = info["seat"]
            self.seat_status[row][col] = "SOLD"

            with self.meta_lock:
                self.sold_count += 1
                self.metrics["purchase_ok"] += 1
                buyer_type = (info.get("buyer_type") or TIPO_NORMAL).lower()
                if buyer_type not in self.purchased_by_type:
                    buyer_type = TIPO_NORMAL
                self.purchased_by_type[buyer_type] += 1
                self._report_progress_milestones_locked()

                if self.sold_count >= TOTAL_ASIENTOS and not self.sold_out_event.is_set():
                    self.sales_finished_at = time.perf_counter()
                    self.sold_out_event.set()

                remaining = TOTAL_ASIENTOS - self.sold_count
                sold_now = self.sold_count
                self.metrics["purchase_time_total"] += time.perf_counter() - started

            return {
                "status": "ok",
                "reservation_id": reservation_id,
                "zone": zone,
                "seat": {"row": row, "col": col},
                "sold_count": sold_now,
                "remaining": remaining,
            }
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
                return {
                    "sold_count": self.sold_count,
                    "reserved_count": reserved_count,
                    "free_count": TOTAL_ASIENTOS - self.sold_count - reserved_count,
                    "buyers_created": len(self.unique_buyers),
                    "seat_status": seat_status_copy,
                }
        finally:
            for lock in reversed(lock_order):
                lock.release()

    def print_summary_once(self):
        with self.meta_lock:
            if self.summary_printed:
                return
            self.summary_printed = True
        self.print_summary()

    def print_summary(self):
        with self.meta_lock:
            if self.sales_started_at is None:
                total_elapsed = 0.0
            elif self.sales_finished_at is None:
                total_elapsed = time.perf_counter() - self.sales_started_at
            else:
                total_elapsed = self.sales_finished_at - self.sales_started_at

            request_count = self.metrics["request_ticket_count"]
            purchase_count = self.metrics["purchase_count"]
            request_avg = self.metrics["request_ticket_time_total"] / request_count if request_count else 0.0
            purchase_avg = self.metrics["purchase_time_total"] / purchase_count if purchase_count else 0.0

            print("\n========== Resumen del Servidor ==========")
            print(f"Asientos totales: {TOTAL_ASIENTOS}")
            print(f"Asientos vendidos: {self.sold_count}")
            print(f"Compradores únicos detectados: {len(self.unique_buyers)}")
            print(f"Reservas activas: {sum(len(self.reservations_by_zone[z]) for z in self.reservations_by_zone)}")
            print(f"Reservas expiradas liberadas: {self.metrics['expired_releases']}")
            print(f"Solicitudes antes del inicio: {self.metrics['not_started_count']}")
            print(f"Tiempo total de ejecución de venta: {total_elapsed:.4f} s")
            print(f"Request_ticket procesados: {request_count}")
            print(f"Compras procesadas: {purchase_count}")
            print(f"Request_ticket exitosos: {self.metrics['request_ticket_ok']}")
            print(f"Compras exitosas: {self.metrics['purchase_ok']}")
            print(f"Compras rechazadas: {self.metrics['purchase_rejected']}")
            print(f"Tiempo promedio request_ticket: {request_avg:.6f} s")
            print(f"Tiempo promedio purchase: {purchase_avg:.6f} s")
            print("==========================================\n")


class TicketServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, server_address, handler_class, ticket_state, expected_clients):
        super().__init__(server_address, handler_class)
        self.ticket_state = ticket_state
        self.expected_clients = expected_clients
        self.registration_lock = threading.Lock()
        self.connected_clients = {}
        self.ready_clients = set()
        self.done_clients = set()
        self.start_event = threading.Event()
        self.all_ready_event = threading.Event()

    def register_client(self, client_id, client_type, buyers_count):
        with self.registration_lock:
            self.connected_clients[client_id] = {
                "client_type": client_type,
                "buyers": buyers_count,
                "connected_at": time.strftime("%H:%M:%S"),
            }
            self.ticket_state.register_client_buyers(client_type, buyers_count)
            connected = len(self.connected_clients)
            return connected

    def mark_ready(self, client_id):
        all_ready = False
        with self.registration_lock:
            self.ready_clients.add(client_id)
            ready_count = len(self.ready_clients)
            connected_count = len(self.connected_clients)

            if (not self.all_ready_event.is_set()
                    and connected_count >= self.expected_clients
                    and ready_count >= self.expected_clients):
                all_ready = True
                self.all_ready_event.set()

        if all_ready:
            with self.ticket_state.terminal_lock:
                print("Todos los clientes esperados están listos. Iniciando cuenta regresiva...")

        return ready_count

    def trigger_start(self):
        with self.registration_lock:
            if self.start_event.is_set():
                return
            self.start_event.set()
        self.ticket_state.open_sales()
        with self.ticket_state.terminal_lock:
            print("Señal START enviada. ¡Venta abierta!")

    def mark_client_done(self, client_id):
        should_close = False
        with self.registration_lock:
            self.done_clients.add(client_id)
            done_count = len(self.done_clients)

            if self.start_event.is_set() and done_count >= self.expected_clients:
                should_close = True

        if should_close:
            self.ticket_state.close_sales("all_clients_done")
            with self.ticket_state.terminal_lock:
                print("Todos los clientes reportaron fin de ejecución. Venta cerrada.")

        return done_count


class TicketRequestHandler(socketserver.StreamRequestHandler):
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

            if message_type == "REGISTER":
                client_id = payload.get("client_id")
                client_type = (payload.get("client_type") or "").lower()
                buyers_count = int(payload.get("buyers", 0))

                if not client_id:
                    self.send_json({"type": "ERROR", "code": "missing_client_id"})
                    continue

                connected = self.server.register_client(client_id, client_type, buyers_count)
                self.send_json({
                    "type": "REGISTERED",
                    "client_id": client_id,
                    "connected_clients": connected,
                    "expected_clients": self.server.expected_clients,
                })
                continue

            if message_type == "READY":
                client_id = payload.get("client_id")
                if not client_id:
                    self.send_json({"type": "ERROR", "code": "missing_client_id"})
                    continue

                ready_count = self.server.mark_ready(client_id)
                self.server.start_event.wait()
                self.send_json({
                    "type": "START",
                    "client_id": client_id,
                    "ready_clients": ready_count,
                    "expected_clients": self.server.expected_clients,
                })
                continue

            if message_type == "REQUEST_TICKET":
                buyer_id = payload.get("buyer_id")
                buyer_type = payload.get("buyer_type", TIPO_NORMAL)
                response = self.server.ticket_state.request_ticket(buyer_id, buyer_type, request_id)
                response["type"] = "REQUEST_TICKET_RESPONSE"
                self.send_json(response)
                continue

            if message_type == "PURCHASE":
                buyer_id = payload.get("buyer_id")
                reservation_id = payload.get("reservation_id")
                response = self.server.ticket_state.purchase(buyer_id, reservation_id, request_id)
                response["type"] = "PURCHASE_RESPONSE"
                self.send_json(response)
                continue

            if message_type == "HEALTH":
                snapshot = self.server.ticket_state.get_snapshot()
                self.send_json({
                    "type": "HEALTH_RESPONSE",
                    "status": "ok",
                    "total_seats": TOTAL_ASIENTOS,
                    "sales_open": self.server.ticket_state.sales_open(),
                    "sales_closed": self.server.ticket_state.sales_closed(),
                    "connected_clients": len(self.server.connected_clients),
                    "ready_clients": len(self.server.ready_clients),
                    "done_clients": len(self.server.done_clients),
                    "expected_clients": self.server.expected_clients,
                    "sold_count": snapshot["sold_count"],
                })
                continue

            if message_type == "CLIENT_DONE":
                client_id = payload.get("client_id")
                if not client_id:
                    self.send_json({"type": "ERROR", "code": "missing_client_id"})
                    continue

                done_count = self.server.mark_client_done(client_id)
                self.send_json({
                    "type": "DONE_ACK",
                    "client_id": client_id,
                    "done_clients": done_count,
                    "expected_clients": self.server.expected_clients,
                })
                continue

            self.send_json({"type": "ERROR", "code": "unknown_message_type"})


class ServerDashboard:
    def __init__(self, ticket_state, server, host, port):
        self.ticket_state = ticket_state
        self.server = server
        self.host = host
        self.port = port

        self.root = tk.Tk()
        self.root.title("Servidor de boletos - Múltiples clientes")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.label_margin = 30
        self.cell_size = 18
        self.grid_width = COLUMNAS * self.cell_size
        self.visual_rows = FILAS + (SECTION_GAP_ROWS * 2) + (SECTION_LABEL_ROWS * 3)
        self.grid_height = self.visual_rows * self.cell_size
        self.canvas_width = self.label_margin + self.grid_width + 10
        self.canvas_height = self.label_margin + self.grid_height + 10
        self.waiting_mode = True
        self.simulation_started = False
        self.countdown_active = False

        self.root.configure(bg="#0a0e27")

        self.waiting_frame = tk.Frame(self.root, bg="#0a0e27")
        self.waiting_frame.pack(fill="both", expand=True)
        self.main_frame = tk.Frame(self.root)

        self.waiting_title = tk.Label(
            self.waiting_frame,
            text="VENTA DE BOLETOS",
            font=("Arial", 28, "bold"),
            fg="#276ef1",
            bg="#0a0e27",
        )
        self.waiting_title.pack(pady=(90, 18))

        self.waiting_label = tk.Label(
            self.waiting_frame,
            text=f"Esperando {self.server.expected_clients} cliente(s)...",
            font=("Arial", 18),
            fg="white",
            bg="#0a0e27",
        )
        self.waiting_label.pack(pady=(0, 10))

        self.waiting_sublabel = tk.Label(
            self.waiting_frame,
            text="0 conectados · 0 listos",
            font=("Arial", 14),
            fg="#a0a8c0",
            bg="#0a0e27",
        )
        self.waiting_sublabel.pack(pady=(0, 25))

        bar_width = min(460, int(self.canvas_width * 0.6))
        bar_height = 34
        self.waiting_bar_canvas = tk.Canvas(
            self.waiting_frame,
            width=bar_width,
            height=bar_height,
            bg="#1a1a3e",
            highlightthickness=1,
            highlightbackground="#333366",
        )
        self.waiting_bar_canvas.pack()
        self.waiting_bar_fill = self.waiting_bar_canvas.create_rectangle(
            0,
            0,
            0,
            bar_height,
            fill="#276ef1",
            outline="",
        )
        self.waiting_bar_text = self.waiting_bar_canvas.create_text(
            bar_width // 2,
            bar_height // 2,
            text="0%",
            fill="white",
            font=("Arial", 11, "bold"),
        )
        self.waiting_bar_width = bar_width
        self.waiting_bar_height = bar_height

        self.main_frame.configure(bg="white")
        self.main_frame.pack(padx=10, pady=10)
        self.main_frame.pack_forget()

        self.canvas = tk.Canvas(self.main_frame, width=self.canvas_width, height=self.canvas_height, bg="white")
        self.canvas.pack(side="left")

        info_frame = tk.Frame(self.main_frame, padx=16)
        info_frame.pack(side="left", fill="y")

        tk.Label(info_frame, text=f"Servidor: {self.host}:{self.port}", font=("Arial", 11), anchor="w").pack(fill="x", pady=(4, 8))

        self.buyers_label = tk.Label(info_frame, text="Compradores detectados: 0", font=("Arial", 11), anchor="w")
        self.buyers_label.pack(fill="x", pady=4)

        self.sold_label = tk.Label(info_frame, text="Asientos vendidos: 0", font=("Arial", 11), anchor="w")
        self.sold_label.pack(fill="x", pady=4)

        self.reserved_label = tk.Label(info_frame, text="Asientos apartados: 0", font=("Arial", 11), anchor="w")
        self.reserved_label.pack(fill="x", pady=4)

        self.free_label = tk.Label(info_frame, text=f"Asientos libres: {TOTAL_ASIENTOS}", font=("Arial", 11), anchor="w")
        self.free_label.pack(fill="x", pady=4)

        tk.Label(info_frame, text="Leyenda", font=("Arial", 11, "bold"), anchor="w").pack(fill="x", pady=(14, 4))
        tk.Label(info_frame, text="Gris: Libre", font=("Arial", 10), anchor="w").pack(fill="x")
        tk.Label(info_frame, text="Naranja: Apartado", font=("Arial", 10), anchor="w").pack(fill="x")
        tk.Label(info_frame, text="Azul: Vendido", font=("Arial", 10), anchor="w").pack(fill="x")

        tk.Label(info_frame, text="Secciones", font=("Arial", 11, "bold"), anchor="w").pack(fill="x", pady=(14, 4))
        tk.Label(info_frame, text="Platino: filas 1-3", font=("Arial", 10), anchor="w").pack(fill="x")
        tk.Label(info_frame, text="Preferente: filas 4-7", font=("Arial", 10), anchor="w").pack(fill="x")
        tk.Label(info_frame, text="Normal: filas 8-30", font=("Arial", 10), anchor="w").pack(fill="x")

        self.radius = int(self.cell_size * 0.35)
        self.seat_items = [[None for _ in range(COLUMNAS)] for _ in range(FILAS)]
        self.last_status = [[None for _ in range(COLUMNAS)] for _ in range(FILAS)]
        self.final_popup_shown = False

        for c in range(COLUMNAS):
            label_x = self.label_margin + c * self.cell_size + self.cell_size // 2
            self.canvas.create_text(label_x, 12, text=str(c + 1), fill="black", font=("Arial", 8))

        for r in range(FILAS):
            visual_row = self._to_visual_row(r)
            label_y = self.label_margin + visual_row * self.cell_size + self.cell_size // 2
            self.canvas.create_text(12, label_y, text=str(r + 1), fill="black", font=("Arial", 8))

        self._draw_zone_guides()
        self._draw_section_labels()

        for r in range(FILAS):
            for c in range(COLUMNAS):
                center_x = self.label_margin + c * self.cell_size + self.cell_size // 2
                visual_row = self._to_visual_row(r)
                center_y = self.label_margin + visual_row * self.cell_size + self.cell_size // 2
                seat = self.canvas.create_oval(
                    center_x - self.radius,
                    center_y - self.radius,
                    center_x + self.radius,
                    center_y + self.radius,
                    fill=self.free_color_for_row(r),
                    outline="black",
                )
                self.seat_items[r][c] = seat

    @staticmethod
    def zone_for_row(row):
        if row <= 2:
            return ZONA_PLATINO
        if row <= 6:
            return ZONA_PREFERENTE
        return ZONA_NORMAL

    @staticmethod
    def free_color_for_row(row):
        zone = ServerDashboard.zone_for_row(row)
        if zone == ZONA_PLATINO:
            return "#B87474"
        if zone == ZONA_PREFERENTE:
            return "#73B27D"
        return "gray"

    def _to_visual_row(self, row):
        offset = SECTION_LABEL_ROWS
        if row >= 3:
            offset += SECTION_GAP_ROWS + SECTION_LABEL_ROWS
        if row >= 7:
            offset += SECTION_GAP_ROWS + SECTION_LABEL_ROWS
        return row + offset

    def _draw_zone_guides(self):
        pref_end_visual_row = self._to_visual_row(2) + 1
        plat_end_visual_row = self._to_visual_row(6) + 1

        y_pref_end = self.label_margin + (pref_end_visual_row * self.cell_size)
        y_plat_end = self.label_margin + (plat_end_visual_row * self.cell_size)

        self.canvas.create_line(self.label_margin, y_pref_end, self.label_margin + self.grid_width, y_pref_end, fill="#9A9A9A", dash=(3, 2))
        self.canvas.create_line(self.label_margin, y_plat_end, self.label_margin + self.grid_width, y_plat_end, fill="#9A9A9A", dash=(3, 2))

    def _draw_section_labels(self):
        center_x = self.label_margin + self.grid_width // 2
        pref_label_row = 0
        plat_label_row = self._to_visual_row(3) - SECTION_LABEL_ROWS
        norm_label_row = self._to_visual_row(7) - SECTION_LABEL_ROWS

        y_pref = self.label_margin + (pref_label_row * self.cell_size) + (self.cell_size // 2)
        y_plat = self.label_margin + (plat_label_row * self.cell_size) + (self.cell_size // 2)
        y_norm = self.label_margin + (norm_label_row * self.cell_size) + (self.cell_size // 2)

        self.canvas.create_text(center_x, y_pref, text="SECCIÓN PLATINO", fill="#7A3F3F", font=("Arial", 9, "bold"))
        self.canvas.create_text(center_x, y_plat, text="SECCIÓN PREFERENTE", fill="#56795E", font=("Arial", 9, "bold"))
        self.canvas.create_text(center_x, y_norm, text="SECCIÓN NORMAL", fill="#555555", font=("Arial", 9, "bold"))

    @staticmethod
    def seat_color(status, row):
        if status == "SOLD":
            return "blue"
        if status == "RESERVED":
            return "orange"
        return ServerDashboard.free_color_for_row(row)

    def refresh(self):
        snapshot = self.ticket_state.get_snapshot()
        status_matrix = snapshot["seat_status"]

        for r in range(FILAS):
            for c in range(COLUMNAS):
                current = status_matrix[r][c]
                if self.last_status[r][c] != current:
                    self.last_status[r][c] = current
                    self.canvas.itemconfig(self.seat_items[r][c], fill=self.seat_color(current, r))

        self.buyers_label.config(text=f"Compradores detectados: {snapshot['buyers_created']}")
        self.sold_label.config(text=f"Asientos vendidos: {snapshot['sold_count']}")
        self.reserved_label.config(text=f"Asientos apartados: {snapshot['reserved_count']}")
        self.free_label.config(text=f"Asientos libres: {snapshot['free_count']}")

        if self.ticket_state.sales_closed() and not self.final_popup_shown:
            self.final_popup_shown = True
            self.show_final_popup(snapshot["sold_count"])
            return

        self.root.after(50, self.refresh)

    def show_final_popup(self, sold_count):
        popup = tk.Toplevel(self.root)
        popup.title("Fin de venta")
        popup.transient(self.root)
        popup.resizable(False, False)

        if sold_count >= TOTAL_ASIENTOS:
            message = "La venta ha concluido"
        else:
            message = f"La venta cerró con {sold_count}/{TOTAL_ASIENTOS} vendidos"

        tk.Label(popup, text=message, font=("Arial", 12), padx=24, pady=20).pack()

        self.root.update_idletasks()
        popup.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - popup.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - popup.winfo_height()) // 2
        popup.geometry(f"+{x}+{y}")

        self.root.after(3000, self.close)

    def _check_ready_phase(self):
        if not self.waiting_mode:
            return

        if self.server.all_ready_event.is_set():
            self._start_countdown()
            return

        with self.server.registration_lock:
            connected = len(self.server.connected_clients)
            ready = len(self.server.ready_clients)

        expected = self.server.expected_clients
        self.waiting_label.config(text=f"Esperando {expected} cliente(s)...")
        self.waiting_sublabel.config(text=f"{connected} conectados \u00b7 {ready} listos")
        self.root.after(200, self._check_ready_phase)

    def _start_countdown(self):
        if self.countdown_active:
            return
        self.countdown_active = True
        self.waiting_label.config(text="\u00a1Todos los clientes listos!")
        self.waiting_sublabel.config(text="La venta inicia en 5 segundos...")
        self.countdown_start = time.time()
        self.countdown_duration = 5.0
        self._update_countdown()

    def _update_countdown(self):
        if not self.waiting_mode:
            return

        elapsed = time.time() - self.countdown_start
        progress = min(elapsed / self.countdown_duration, 1.0)
        fill_width = int(self.waiting_bar_width * progress)

        self.waiting_bar_canvas.coords(
            self.waiting_bar_fill, 0, 0, fill_width, self.waiting_bar_height
        )
        percent = int(progress * 100)
        self.waiting_bar_canvas.itemconfig(self.waiting_bar_text, text=f"{percent}%")

        remaining = max(0.0, self.countdown_duration - elapsed)
        if remaining > 0:
            secs_left = int(remaining) + (1 if remaining > int(remaining) else 0)
            self.waiting_sublabel.config(text=f"La venta inicia en {secs_left} segundos...")

        if progress >= 1.0:
            self.waiting_sublabel.config(text="\u00a1Venta abierta!")
            self.root.after(250, self._show_simulation_view)
            return

        self.root.after(50, self._update_countdown)

    def _show_simulation_view(self):
        if not self.waiting_mode:
            return
        self.waiting_mode = False
        self.waiting_frame.pack_forget()
        self.root.configure(bg="white")
        self.main_frame.pack(padx=10, pady=10)

        if not self.simulation_started:
            self.simulation_started = True
            self.server.trigger_start()
            self.refresh()

    def run(self):
        self._check_ready_phase()
        self.root.mainloop()

    def close(self):
        try:
            self.server.shutdown()
        except Exception:
            pass
        try:
            self.server.server_close()
        except Exception:
            pass

        self.ticket_state.print_summary_once()

        if self.root.winfo_exists():
            self.root.destroy()


def cleanup_expired_reservations(ticket_state):
    while not ticket_state.sold_out_event.is_set():
        if ticket_state.sales_open_event.is_set():
            for zone in (ZONA_PLATINO, ZONA_PREFERENTE, ZONA_NORMAL):
                zone_lock = ticket_state.zone_locks[zone]
                acquired = zone_lock.acquire(timeout=0.05)
                if acquired:
                    try:
                        ticket_state._cleanup_expired_zone_locked(zone)
                    finally:
                        zone_lock.release()
        time.sleep(0.25)


def monitor_sold_out(ticket_state):
    ticket_state.sold_out_event.wait()
    with ticket_state.meta_lock:
        sold_count = ticket_state.sold_count
        close_reason = ticket_state.close_reason
        need_100 = 100 not in ticket_state.hitos_reportados
        if sold_count >= TOTAL_ASIENTOS and need_100:
            ticket_state.hitos_reportados.add(100)

    with ticket_state.terminal_lock:
        if sold_count >= TOTAL_ASIENTOS and need_100:
            print(f"Actualización: 100% de boletos vendidos ({sold_count}/{TOTAL_ASIENTOS}).")
        if close_reason == "all_clients_done" and sold_count < TOTAL_ASIENTOS:
            print(f"Actualización: venta cerrada por fin de clientes ({sold_count}/{TOTAL_ASIENTOS} vendidos).")
        if close_reason == "unsellable_remaining":
            print(f"Actualización: venta cerrada porque los asientos restantes no tienen compradores elegibles ({sold_count}/{TOTAL_ASIENTOS} vendidos).")
        print("Actualización: la venta ha concluido.")

    ticket_state.print_summary_once()


def parse_args():
    parser = argparse.ArgumentParser(description="Servidor de boletos - Múltiples clientes")
    parser.add_argument("expected_clients", type=int, help="Cantidad de clientes que deben conectarse antes de iniciar")
    parser.add_argument("--host", default="127.0.0.1", help="Host para escuchar conexiones")
    parser.add_argument("--port", type=int, default=5000, help="Puerto para escuchar conexiones")
    parser.add_argument("--no-gui", action="store_true", help="Ejecuta el servidor sin visualización")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.expected_clients <= 0:
        raise ValueError("expected_clients debe ser mayor que 0")

    expected_clients = args.expected_clients

    ticket_state = TicketState()
    server = TicketServer((args.host, args.port), TicketRequestHandler, ticket_state, expected_clients)

    monitor_thread = threading.Thread(target=monitor_sold_out, args=(ticket_state,), daemon=True)
    monitor_thread.start()

    cleanup_thread = threading.Thread(target=cleanup_expired_reservations, args=(ticket_state,), daemon=True)
    cleanup_thread.start()

    print("Servidor de boletos iniciado")
    print(f"Escuchando en {args.host}:{args.port}")
    print(f"Asientos disponibles: {TOTAL_ASIENTOS}")
    print(f"Clientes esperados para iniciar: {expected_clients}")
    print("Zonas: PLATINO (filas 1-3), PREFERENTE (4-7), NORMAL (8-30)")

    if args.no_gui:
        def wait_and_start():
            server.all_ready_event.wait()
            for i in range(5, 0, -1):
                print(f"  Iniciando en {i}...")
                time.sleep(1)
            server.trigger_start()

        countdown_thread = threading.Thread(target=wait_and_start, daemon=True)
        countdown_thread.start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[Servidor] Interrupción recibida. Cerrando servidor...")
        finally:
            server.shutdown()
            server.server_close()
            ticket_state.print_summary_once()
        return

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        dashboard = ServerDashboard(ticket_state, server, args.host, args.port)
        dashboard.run()
    except tk.TclError:
        print("[Servidor] No fue posible iniciar la interfaz. Ejecuta con --no-gui o revisa tu entorno gráfico.")
        server.shutdown()
        server.server_close()
        ticket_state.print_summary_once()
    except KeyboardInterrupt:
        print("\n[Servidor] Interrupción recibida. Cerrando servidor...")
        server.shutdown()
        server.server_close()
        ticket_state.print_summary_once()
    finally:
        pass


if __name__ == "__main__":
    main()
