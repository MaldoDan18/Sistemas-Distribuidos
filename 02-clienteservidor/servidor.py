import argparse
import json
import random
import socketserver
import threading
import time
import tkinter as tk
import uuid

FILAS = 25
COLUMNAS = 40
TOTAL_ASIENTOS = FILAS * COLUMNAS
TOTAL_COMPRADORES_ESPERADOS = TOTAL_ASIENTOS * 2
RESERVA_TTL_SEGUNDOS = 3.0


class TicketState:
    def __init__(self):
        self.state_lock = threading.Lock()
        self.terminal_lock = threading.Lock()
        self.seat_status = [["FREE" for _ in range(COLUMNAS)] for _ in range(FILAS)]
        self.free_seats = {(r, c) for r in range(FILAS) for c in range(COLUMNAS)}
        self.reservations = {}
        self.sold_count = 0

        self.sales_started_at = None
        self.sales_finished_at = None
        self.sold_out_event = threading.Event()
        self.sales_open_event = threading.Event()
        self.summary_printed = False

        self.history = []
        self.unique_buyers = set()
        self.hitos_reportados = set()

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

    def _log_event(self, request_id, buyer_id, action, result, seat=None, reservation_id=None, extra=None):
        event = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "request_id": request_id,
            "buyer_id": buyer_id,
            "action": action,
            "result": result,
            "seat": seat,
            "reservation_id": reservation_id,
        }
        if extra is not None:
            event["extra"] = extra
        self.history.append(event)

    def _cleanup_expired_locked(self):
        now = time.monotonic()
        expired = [
            reservation_id
            for reservation_id, info in self.reservations.items()
            if info["expires_at"] <= now
        ]

        for reservation_id in expired:
            info = self.reservations.pop(reservation_id)
            row, col = info["seat"]
            self.seat_status[row][col] = "FREE"
            self.free_seats.add((row, col))
            self.metrics["expired_releases"] += 1
            self._log_event(
                request_id=f"server-expire-{reservation_id}",
                buyer_id=info["buyer_id"],
                action="EXPIRE_RESERVATION",
                result="RELEASED",
                seat={"row": row, "col": col},
                reservation_id=reservation_id,
            )

    def open_sales(self):
        with self.state_lock:
            if self.sales_open_event.is_set():
                return
            self.sales_started_at = time.perf_counter()
            self.sales_open_event.set()

        with self.terminal_lock:
            print("Actualizaciones de venta:")

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

    def register_buyer(self, buyer_id):
        if buyer_id is None:
            return
        with self.state_lock:
            self.unique_buyers.add(str(buyer_id))

    def sales_open(self):
        return self.sales_open_event.is_set()

    def request_ticket(self, buyer_id, request_id):
        started = time.perf_counter()

        with self.state_lock:
            if not self.sales_open_event.is_set():
                self.metrics["not_started_count"] += 1
                response = {
                    "status": "not_started",
                    "message": "La venta aún no inicia.",
                }
            else:
                self._cleanup_expired_locked()
                self.metrics["request_ticket_count"] += 1

                if self.sold_count >= TOTAL_ASIENTOS or not self.free_seats:
                    self._log_event(request_id, buyer_id, "REQUEST_TICKET", "SOLD_OUT")
                    response = {
                        "status": "sold_out",
                        "message": "No hay asientos disponibles.",
                    }
                else:
                    seat = random.choice(tuple(self.free_seats))
                    row, col = seat
                    reservation_id = str(uuid.uuid4())
                    expires_at = time.monotonic() + RESERVA_TTL_SEGUNDOS

                    self.free_seats.remove(seat)
                    self.seat_status[row][col] = "RESERVED"
                    self.reservations[reservation_id] = {
                        "buyer_id": buyer_id,
                        "seat": seat,
                        "expires_at": expires_at,
                    }

                    self.metrics["request_ticket_ok"] += 1
                    self._log_event(
                        request_id,
                        buyer_id,
                        "REQUEST_TICKET",
                        "RESERVED",
                        seat={"row": row, "col": col},
                        reservation_id=reservation_id,
                    )
                    response = {
                        "status": "ok",
                        "reservation_id": reservation_id,
                        "seat": {"row": row, "col": col},
                        "ttl_seconds": RESERVA_TTL_SEGUNDOS,
                    }

            elapsed = time.perf_counter() - started
            self.metrics["request_ticket_time_total"] += elapsed
            return response

    def purchase(self, buyer_id, request_id, reservation_id):
        started = time.perf_counter()

        with self.state_lock:
            if not self.sales_open_event.is_set():
                self.metrics["not_started_count"] += 1
                response = {
                    "status": "not_started",
                    "message": "La venta aún no inicia.",
                }
            else:
                self._cleanup_expired_locked()
                self.metrics["purchase_count"] += 1

                if self.sold_count >= TOTAL_ASIENTOS:
                    self._log_event(request_id, buyer_id, "PURCHASE", "SOLD_OUT", reservation_id=reservation_id)
                    response = {
                        "status": "sold_out",
                        "message": "La venta terminó.",
                    }
                else:
                    info = self.reservations.get(reservation_id)
                    if info is None:
                        self.metrics["purchase_rejected"] += 1
                        self._log_event(
                            request_id,
                            buyer_id,
                            "PURCHASE",
                            "INVALID_OR_EXPIRED_RESERVATION",
                            reservation_id=reservation_id,
                        )
                        response = {
                            "status": "error",
                            "code": "invalid_or_expired_reservation",
                        }
                    elif info["buyer_id"] != buyer_id:
                        self.metrics["purchase_rejected"] += 1
                        row, col = info["seat"]
                        self._log_event(
                            request_id,
                            buyer_id,
                            "PURCHASE",
                            "FORBIDDEN",
                            seat={"row": row, "col": col},
                            reservation_id=reservation_id,
                        )
                        response = {
                            "status": "error",
                            "code": "reservation_owner_mismatch",
                        }
                    else:
                        row, col = info["seat"]
                        self.reservations.pop(reservation_id, None)
                        self.seat_status[row][col] = "SOLD"
                        self.sold_count += 1
                        self._report_progress_milestones_locked()
                        self.metrics["purchase_ok"] += 1
                        self._log_event(
                            request_id,
                            buyer_id,
                            "PURCHASE",
                            "SOLD",
                            seat={"row": row, "col": col},
                            reservation_id=reservation_id,
                        )

                        if self.sold_count >= TOTAL_ASIENTOS and not self.sold_out_event.is_set():
                            self.sales_finished_at = time.perf_counter()
                            self.sold_out_event.set()

                        response = {
                            "status": "ok",
                            "seat": {"row": row, "col": col},
                            "sold_count": self.sold_count,
                            "remaining": TOTAL_ASIENTOS - self.sold_count,
                        }

            elapsed = time.perf_counter() - started
            self.metrics["purchase_time_total"] += elapsed
            return response

    def get_snapshot(self):
        with self.state_lock:
            reserved_count = len(self.reservations)
            free_count = TOTAL_ASIENTOS - self.sold_count - reserved_count
            seat_status_copy = [row[:] for row in self.seat_status]
            return {
                "sold_count": self.sold_count,
                "reserved_count": reserved_count,
                "free_count": free_count,
                "seat_status": seat_status_copy,
                "buyers_created": len(self.unique_buyers),
            }

    def print_summary_once(self):
        with self.state_lock:
            if self.summary_printed:
                return
            self.summary_printed = True
        self.print_summary()

    def print_summary(self):
        with self.state_lock:
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
            print(f"Compradores esperados (doble): {TOTAL_COMPRADORES_ESPERADOS}")
            print(f"Compradores creados (únicos): {len(self.unique_buyers)}")
            print(f"Asientos restantes: {TOTAL_ASIENTOS - self.sold_count}")
            print(f"Reservas activas: {len(self.reservations)}")
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


class TicketRequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.server.register_connection()
        while True:
            raw_line = self.rfile.readline()
            if not raw_line:
                return

            try:
                payload = json.loads(raw_line.decode("utf-8").strip())
            except json.JSONDecodeError:
                response = {"status": "error", "code": "invalid_json"}
                self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
                self.wfile.flush()
                continue

            action = payload.get("action")
            buyer_id = payload.get("buyer_id")
            request_id = payload.get("request_id", str(uuid.uuid4()))

            self.server.ticket_state.register_buyer(buyer_id)

            if action == "request_ticket":
                response = self.server.ticket_state.request_ticket(buyer_id, request_id)
            elif action == "purchase":
                reservation_id = payload.get("reservation_id")
                if not reservation_id:
                    response = {"status": "error", "code": "missing_reservation_id"}
                else:
                    response = self.server.ticket_state.purchase(buyer_id, request_id, reservation_id)
            elif action == "health":
                snapshot = self.server.ticket_state.get_snapshot()
                response = {
                    "status": "ok",
                    "sold_count": snapshot["sold_count"],
                    "remaining": snapshot["free_count"] + snapshot["reserved_count"],
                    "sales_open": self.server.ticket_state.sales_open(),
                }
            else:
                response = {"status": "error", "code": "unknown_action"}

            self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
            self.wfile.flush()


class TicketServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, server_address, request_handler_class, ticket_state):
        super().__init__(server_address, request_handler_class)
        self.ticket_state = ticket_state
        self.first_client_event = threading.Event()
        self.connection_count = 0
        self.connection_lock = threading.Lock()

    def register_connection(self):
        with self.connection_lock:
            self.connection_count += 1
            self.first_client_event.set()


class ServerDashboard:
    def __init__(self, ticket_state, server, host, port):
        self.ticket_state = ticket_state
        self.server = server
        self.host = host
        self.port = port

        self.root = tk.Tk()
        self.root.title("Servidor de boletos - Visualización")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.label_margin = 30
        self.cell_size = 18
        self.grid_width = COLUMNAS * self.cell_size
        self.grid_height = FILAS * self.cell_size
        self.canvas_width = self.label_margin + self.grid_width + 10
        self.canvas_height = self.label_margin + self.grid_height + 10

        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(padx=10, pady=10)

        self.canvas = tk.Canvas(self.main_frame, width=self.canvas_width, height=self.canvas_height, bg="white")
        self.canvas.pack(side="left")

        self.info_frame = tk.Frame(self.main_frame, padx=16)
        self.info_frame.pack(side="left", fill="y")

        self.status_label = tk.Label(
            self.info_frame,
            text=f"Servidor escuchando: {self.host}:{self.port}",
            font=("Arial", 11),
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(4, 8))

        self.sold_label = tk.Label(self.info_frame, text="Asientos vendidos: 0", font=("Arial", 11), anchor="w")
        self.sold_label.pack(fill="x", pady=4)

        self.buyers_expected_label = tk.Label(
            self.info_frame,
            text=f"Compradores esperados: {TOTAL_COMPRADORES_ESPERADOS}",
            font=("Arial", 11),
            anchor="w",
        )
        self.buyers_expected_label.pack(fill="x", pady=4)

        self.buyers_label = tk.Label(self.info_frame, text="Compradores creados: 0", font=("Arial", 11), anchor="w")
        self.buyers_label.pack(fill="x", pady=4)

        self.reserved_label = tk.Label(self.info_frame, text="Asientos apartados: 0", font=("Arial", 11), anchor="w")
        self.reserved_label.pack(fill="x", pady=4)

        self.free_label = tk.Label(self.info_frame, text=f"Asientos libres: {TOTAL_ASIENTOS}", font=("Arial", 11), anchor="w")
        self.free_label.pack(fill="x", pady=4)

        legend_title = tk.Label(self.info_frame, text="Leyenda", font=("Arial", 11, "bold"), anchor="w")
        legend_title.pack(fill="x", pady=(14, 4))
        tk.Label(self.info_frame, text="Gris: Libre", font=("Arial", 10), anchor="w").pack(fill="x")
        tk.Label(self.info_frame, text="Naranja: Apartado", font=("Arial", 10), anchor="w").pack(fill="x")
        tk.Label(self.info_frame, text="Azul: Vendido", font=("Arial", 10), anchor="w").pack(fill="x")

        self.radius = int(self.cell_size * 0.35)
        self.seat_items = [[None for _ in range(COLUMNAS)] for _ in range(FILAS)]
        self.last_status = [[None for _ in range(COLUMNAS)] for _ in range(FILAS)]
        self.final_popup_shown = False

        for c in range(COLUMNAS):
            label_x = self.label_margin + c * self.cell_size + self.cell_size // 2
            self.canvas.create_text(label_x, 12, text=str(c + 1), fill="black", font=("Arial", 8))

        for r in range(FILAS):
            label_y = self.label_margin + r * self.cell_size + self.cell_size // 2
            self.canvas.create_text(12, label_y, text=str(r + 1), fill="black", font=("Arial", 8))

        for r in range(FILAS):
            for c in range(COLUMNAS):
                center_x = self.label_margin + c * self.cell_size + self.cell_size // 2
                center_y = self.label_margin + r * self.cell_size + self.cell_size // 2
                seat = self.canvas.create_oval(
                    center_x - self.radius,
                    center_y - self.radius,
                    center_x + self.radius,
                    center_y + self.radius,
                    fill="gray",
                    outline="black",
                )
                self.seat_items[r][c] = seat

    @staticmethod
    def seat_color(status):
        if status == "SOLD":
            return "blue"
        if status == "RESERVED":
            return "orange"
        return "gray"

    def show_start_countdown(self, seconds=3):
        popup = tk.Toplevel(self.root)
        popup.title("Inicio de venta")
        popup.transient(self.root)
        popup.resizable(False, False)

        message_label = tk.Label(popup, font=("Arial", 12), padx=20, pady=18)
        message_label.pack()

        def center_popup():
            self.root.update_idletasks()
            popup.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - popup.winfo_width()) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - popup.winfo_height()) // 2
            popup.geometry(f"+{x}+{y}")

        def tick(remaining):
            if remaining > 0:
                suffix = "segundo" if remaining == 1 else "segundos"
                message_label.config(text=f"La venta iniciará en {remaining} {suffix}")
                center_popup()
                self.root.after(1000, tick, remaining - 1)
                return

            popup.destroy()
            self.ticket_state.open_sales()

        tick(seconds)

    def show_client_connected_popup(self, callback_after_close):
        popup = tk.Toplevel(self.root)
        popup.title("Depuración")
        popup.transient(self.root)
        popup.resizable(False, False)

        message_label = tk.Label(popup, text="¡Cliente conectado!", font=("Arial", 12), padx=24, pady=18)
        message_label.pack()

        self.root.update_idletasks()
        popup.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - popup.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - popup.winfo_height()) // 2
        popup.geometry(f"+{x}+{y}")

        def finish_popup():
            if popup.winfo_exists():
                popup.destroy()
            callback_after_close()

        self.root.after(1000, finish_popup)

    def wait_for_client_then_start(self):
        popup = tk.Toplevel(self.root)
        popup.title("Esperando cliente")
        popup.transient(self.root)
        popup.resizable(False, False)

        message_label = tk.Label(popup, text="Esperando conexión de cliente...", font=("Arial", 12), padx=24, pady=18)
        message_label.pack()

        self.root.update_idletasks()
        popup.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - popup.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - popup.winfo_height()) // 2
        popup.geometry(f"+{x}+{y}")

        def check_connection():
            if self.server.first_client_event.is_set():
                if popup.winfo_exists():
                    popup.destroy()
                self.show_client_connected_popup(lambda: self.show_start_countdown(3))
                return
            self.root.after(200, check_connection)

        check_connection()

    def refresh(self):
        snapshot = self.ticket_state.get_snapshot()
        status_matrix = snapshot["seat_status"]

        for r in range(FILAS):
            for c in range(COLUMNAS):
                current = status_matrix[r][c]
                if self.last_status[r][c] != current:
                    self.last_status[r][c] = current
                    self.canvas.itemconfig(self.seat_items[r][c], fill=self.seat_color(current))

        self.sold_label.config(text=f"Asientos vendidos: {snapshot['sold_count']}")
        self.buyers_label.config(text=f"Compradores creados: {snapshot['buyers_created']}")
        self.reserved_label.config(text=f"Asientos apartados: {snapshot['reserved_count']}")
        self.free_label.config(text=f"Asientos libres: {snapshot['free_count']}")

        if snapshot["sold_count"] >= TOTAL_ASIENTOS and not self.final_popup_shown:
            self.final_popup_shown = True
            self.ticket_state.print_summary_once()
            self.show_final_popup()
            return

        self.root.after(50, self.refresh)

    def show_final_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Fin de venta")
        popup.transient(self.root)
        popup.resizable(False, False)

        message_label = tk.Label(popup, text="La venta ha concluido", font=("Arial", 12), padx=24, pady=20)
        message_label.pack()

        self.root.update_idletasks()
        popup.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - popup.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - popup.winfo_height()) // 2
        popup.geometry(f"+{x}+{y}")

        self.root.after(3000, self.close)

    def run(self):
        self.wait_for_client_then_start()
        self.refresh()
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


def monitor_sold_out(ticket_state):
    ticket_state.sold_out_event.wait()
    with ticket_state.state_lock:
        sold_count = ticket_state.sold_count
        need_100 = 100 not in ticket_state.hitos_reportados
        if need_100:
            ticket_state.hitos_reportados.add(100)

    with ticket_state.terminal_lock:
        if need_100:
            print(f"Actualización: 100% de boletos vendidos ({sold_count}/{TOTAL_ASIENTOS}).")
        print("Actualización: la venta ha concluido.")


def parse_args():
    parser = argparse.ArgumentParser(description="Servidor de boletos - Práctica 2 Fase 1")
    parser.add_argument("--host", default="127.0.0.1", help="Host para escuchar conexiones")
    parser.add_argument("--port", type=int, default=5000, help="Puerto para escuchar conexiones")
    parser.add_argument("--no-gui", action="store_true", help="Ejecuta el servidor sin visualización")
    return parser.parse_args()


def main():
    args = parse_args()
    ticket_state = TicketState()
    server = TicketServer((args.host, args.port), TicketRequestHandler, ticket_state)

    monitor_thread = threading.Thread(target=monitor_sold_out, args=(ticket_state,), daemon=True)
    monitor_thread.start()

    print("Servidor de boletos iniciado")
    print(f"Escuchando en {args.host}:{args.port}")
    print(f"Asientos disponibles: {TOTAL_ASIENTOS}")
    print("Visualización: desactivada" if args.no_gui else "Visualización: activada")

    if args.no_gui:
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        print("Esperando conexión de cliente...")
        server.first_client_event.wait()
        print("¡Cliente conectado!")

        for remaining in range(3, 0, -1):
            suffix = "segundo" if remaining == 1 else "segundos"
            print(f"La venta iniciará en {remaining} {suffix}")
            time.sleep(1)
        print("Iniciando venta...")
        ticket_state.open_sales()

        try:
            while not ticket_state.sold_out_event.is_set():
                time.sleep(0.2)
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


if __name__ == "__main__":
    main()
