# Practica 6 - Servicios

import argparse
import json
import socketserver
import threading
import tkinter as tk


STATUS_GRAY = "gray"
STATUS_BLUE = "blue"
STATUS_ORANGE = "orange"
STATUS_GREEN = "green"

STATUS_COLORS = {
    STATUS_GRAY: "#8d8d8d",
    STATUS_BLUE: "#2c6bed",
    STATUS_ORANGE: "#f28b25",
    STATUS_GREEN: "#2bbf6a",
}


class CoordinatorState:
    def __init__(self, expected_servers):
        self.expected_servers = expected_servers
        self.lock = threading.Lock()
        self.global_started = False

        self.handlers_by_sale = {}
        self.sale_to_slot = {}
        self.slot_to_sale = [None for _ in range(expected_servers)]
        self.pending_clients_by_sale = {}

        self.server_info_by_sale = {}

    def _first_available_slot_locked(self):
        for idx, sale_id in enumerate(self.slot_to_sale):
            if sale_id is None:
                return idx
        return None

    def register_server(self, sale_id, handler, expected_clients, server_host, server_port):
        with self.lock:
            if sale_id in self.sale_to_slot:
                slot = self.sale_to_slot[sale_id]
            else:
                slot = self._first_available_slot_locked()
                if slot is None:
                    return None, "capacity_reached"
                self.sale_to_slot[sale_id] = slot
                self.slot_to_sale[slot] = sale_id

            pending_clients = self.pending_clients_by_sale.pop(sale_id, {})
            info = self.server_info_by_sale.get(
                sale_id,
                {
                    "slot": slot,
                    "expected_clients": int(expected_clients),
                    "connected_clients": set(),
                    "client_buyers": {},
                    "total_buyer_threads": 0,
                    "status": STATUS_GRAY,
                    "server_host": server_host,
                    "server_port": server_port,
                    "finish_summary": None,
                },
            )

            info["slot"] = slot
            info["expected_clients"] = max(0, int(expected_clients))
            info["status"] = STATUS_BLUE
            info["server_host"] = server_host
            info["server_port"] = server_port
            for client_id, buyers in pending_clients.items():
                if client_id not in info["connected_clients"]:
                    info["connected_clients"].add(client_id)
                    info["client_buyers"][client_id] = max(0, int(buyers))
            info["total_buyer_threads"] = sum(info["client_buyers"].values())

            self.server_info_by_sale[sale_id] = info
            self.handlers_by_sale[sale_id] = handler

            should_start = self._maybe_mark_global_start_locked()
            return {
                "slot": slot,
                "registered_servers": len(self.handlers_by_sale),
                "expected_servers": self.expected_servers,
                "connected_clients": len(info["connected_clients"]),
                "expected_clients": info["expected_clients"],
                "total_buyer_threads": info["total_buyer_threads"],
            }, should_start

    def unregister_server_connection(self, sale_id, handler):
        with self.lock:
            current = self.handlers_by_sale.get(sale_id)
            if current is handler:
                self.handlers_by_sale.pop(sale_id, None)

    def register_client_connected(self, sale_id, client_id, buyers_count):
        buyers_count = max(0, int(buyers_count))
        with self.lock:
            if sale_id in self.server_info_by_sale:
                info = self.server_info_by_sale[sale_id]
                if client_id not in info["connected_clients"]:
                    info["connected_clients"].add(client_id)
                    info["client_buyers"][client_id] = buyers_count
                    info["total_buyer_threads"] = sum(info["client_buyers"].values())
                connected = len(info["connected_clients"])
                expected = info["expected_clients"]
                total_buyer_threads = info["total_buyer_threads"]
            else:
                pending = self.pending_clients_by_sale.setdefault(sale_id, {})
                pending.setdefault(client_id, buyers_count)
                connected = len(pending)
                expected = None
                total_buyer_threads = sum(pending.values())

            should_start = self._maybe_mark_global_start_locked()
            return connected, expected, total_buyer_threads, should_start

    def mark_server_finished(self, sale_id, finish_summary):
        with self.lock:
            if sale_id not in self.server_info_by_sale:
                return False
            self.server_info_by_sale[sale_id]["status"] = STATUS_GREEN
            if isinstance(finish_summary, dict):
                self.server_info_by_sale[sale_id]["finish_summary"] = finish_summary
            return True

    def _all_servers_registered_locked(self):
        return len(self.handlers_by_sale) >= self.expected_servers

    def _all_clients_connected_locked(self):
        if not self._all_servers_registered_locked():
            return False

        for sale_id in self.handlers_by_sale:
            info = self.server_info_by_sale.get(sale_id)
            if info is None:
                return False
            if len(info["connected_clients"]) < info["expected_clients"]:
                return False
        return True

    def _maybe_mark_global_start_locked(self):
        if self.global_started:
            return False
        if not self._all_clients_connected_locked():
            return False

        self.global_started = True
        for sale_id in self.handlers_by_sale:
            info = self.server_info_by_sale.get(sale_id)
            if info is not None:
                info["status"] = STATUS_ORANGE
        return True

    def broadcast_global_start(self):
        with self.lock:
            handlers = list(self.handlers_by_sale.values())

        for handler in handlers:
            handler.send_json(
                {
                    "type": "GLOBAL_START",
                    "message": "Todos los clientes de todos los servidores están conectados.",
                }
            )

    def get_snapshot(self):
        with self.lock:
            slots = []
            for slot_index in range(self.expected_servers):
                sale_id = self.slot_to_sale[slot_index]
                if sale_id is None:
                    slots.append(
                        {
                            "slot": slot_index,
                            "sale_id": None,
                            "status": STATUS_GRAY,
                            "expected_clients": 0,
                            "connected_clients": 0,
                            "total_buyer_threads": 0,
                            "finish_summary": None,
                        }
                    )
                    continue

                info = self.server_info_by_sale.get(sale_id)
                if info is None:
                    slots.append(
                        {
                            "slot": slot_index,
                            "sale_id": sale_id,
                            "status": STATUS_GRAY,
                            "expected_clients": 0,
                            "connected_clients": 0,
                            "total_buyer_threads": 0,
                            "finish_summary": None,
                        }
                    )
                    continue

                slots.append(
                    {
                        "slot": slot_index,
                        "sale_id": sale_id,
                        "status": info["status"],
                        "expected_clients": info["expected_clients"],
                        "connected_clients": len(info["connected_clients"]),
                        "total_buyer_threads": info["total_buyer_threads"],
                        "finish_summary": info.get("finish_summary"),
                    }
                )

            return {
                "expected_servers": self.expected_servers,
                "registered_servers": len(self.handlers_by_sale),
                "global_started": self.global_started,
                "slots": slots,
            }

class CoordinatorServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, server_address, handler_class, state):
        super().__init__(server_address, handler_class)
        self.state = state


class CoordinatorHandler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.sale_id = None

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

            if message_type == "SERVER_REGISTER":
                sale_id = str(payload.get("sale_id") or "").strip()
                if not sale_id:
                    self.send_json({"type": "ERROR", "code": "missing_sale_id"})
                    continue

                expected_clients = int(payload.get("expected_clients", 0))
                server_host = payload.get("server_host")
                server_port = payload.get("server_port")

                result, start_now = self.server.state.register_server(
                    sale_id,
                    self,
                    expected_clients,
                    server_host,
                    server_port,
                )
                if result is None:
                    self.send_json(
                        {
                            "type": "ERROR",
                            "code": "capacity_reached",
                            "message": "No hay slots disponibles en el coordinador.",
                        }
                    )
                    continue

                self.sale_id = sale_id
                self.send_json(
                    {
                        "type": "REGISTERED_ACK",
                        "sale_id": sale_id,
                        "slot": result["slot"],
                        "registered_servers": result["registered_servers"],
                        "expected_servers": result["expected_servers"],
                        "connected_clients": result["connected_clients"],
                        "expected_clients": result["expected_clients"],
                    }
                )

                if start_now:
                    print("[Coordinador] Condición global cumplida. Enviando GLOBAL_START.")
                    self.server.state.broadcast_global_start()
                continue

            if message_type == "SERVER_DISCONNECT":
                sale_id = str(payload.get("sale_id") or "").strip()
                if sale_id:
                    self.server.state.unregister_server_connection(sale_id, self)
                    self.send_json({"type": "SERVER_DISCONNECT_ACK", "sale_id": sale_id})
                else:
                    self.send_json({"type": "ERROR", "code": "missing_sale_id"})
                continue

            if message_type == "CLIENT_CONNECTED":
                sale_id = str(payload.get("sale_id") or "").strip()
                client_id = str(payload.get("client_id") or "").strip()
                buyers_count = int(payload.get("buyers", 0))
                if not sale_id:
                    self.send_json({"type": "ERROR", "code": "missing_sale_id"})
                    continue
                if not client_id:
                    self.send_json({"type": "ERROR", "code": "missing_client_id"})
                    continue

                connected, expected, total_buyers, start_now = self.server.state.register_client_connected(
                    sale_id,
                    client_id,
                    buyers_count,
                )
                self.send_json(
                    {
                        "type": "CLIENT_CONNECTED_ACK",
                        "sale_id": sale_id,
                        "client_id": client_id,
                        "connected_clients": connected,
                        "expected_clients": expected,
                        "total_buyer_threads": total_buyers,
                    }
                )

                if start_now:
                    print("[Coordinador] Condición global cumplida. Enviando GLOBAL_START.")
                    self.server.state.broadcast_global_start()
                continue

            if message_type == "SERVER_FINISHED":
                sale_id = str(payload.get("sale_id") or "").strip()
                finish_summary = payload.get("finish_summary")
                if not sale_id:
                    self.send_json({"type": "ERROR", "code": "missing_sale_id"})
                    continue

                ok = self.server.state.mark_server_finished(sale_id, finish_summary)
                if not ok:
                    self.send_json({"type": "ERROR", "code": "unknown_server"})
                else:
                    self.send_json({"type": "SERVER_FINISHED_ACK", "sale_id": sale_id})
                continue

            if message_type == "HEALTH":
                snapshot = self.server.state.get_snapshot()
                self.send_json({"type": "HEALTH_RESPONSE", "status": "ok", "snapshot": snapshot})
                continue

            self.send_json({"type": "ERROR", "code": "unknown_message_type"})

    def finish(self):
        if self.sale_id:
            self.server.state.unregister_server_connection(self.sale_id, self)
        super().finish()


class CoordinatorDashboard:
    def __init__(self, state, host, port):
        self.state = state
        self.host = host
        self.port = port

        self.root = tk.Tk()
        self.root.title("Coordinador global de ventas")
        self.root.configure(bg="#0a0e27")

        header = tk.Frame(self.root, bg="#0a0e27")
        header.pack(fill="x", padx=12, pady=(10, 8))

        tk.Label(
            header,
            text=f"Coordinador: {host}:{port}",
            fg="white",
            bg="#0a0e27",
            font=("Arial", 11, "bold"),
        ).pack(anchor="w")

        self.status_label = tk.Label(
            header,
            text="Esperando servidores...",
            fg="#aab4d6",
            bg="#0a0e27",
            font=("Arial", 10),
        )
        self.status_label.pack(anchor="w", pady=(4, 0))

        self.grid_frame = tk.Frame(self.root, bg="#0a0e27")
        self.grid_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        self.server_name_labels = []
        self.server_state_cells = []
        self.client_progress_canvases = []
        self.client_progress_text = []

        self._build_grid()

    def _build_grid(self):
        total = self.state.expected_servers
        for col in range(total):
            self.grid_frame.columnconfigure(col, weight=1, uniform="server-col")

            title = tk.Label(
                self.grid_frame,
                text=f"Servidor {col + 1}",
                bg="#0a0e27",
                fg="#dce3ff",
                font=("Arial", 10, "bold"),
                padx=8,
                pady=8,
            )
            title.grid(row=0, column=col, padx=6, pady=(0, 6), sticky="ew")
            self.server_name_labels.append(title)

            state_cell = tk.Label(
                self.grid_frame,
                text="Sin conexión",
                bg=STATUS_COLORS[STATUS_GRAY],
                fg="white",
                font=("Arial", 10, "bold"),
                height=2,
                relief="groove",
                bd=2,
            )
            state_cell.grid(row=1, column=col, padx=6, pady=(0, 8), sticky="ew")
            self.server_state_cells.append(state_cell)

            progress_canvas = tk.Canvas(
                self.grid_frame,
                height=66,
                bg="#5b1d1d",
                highlightthickness=1,
                highlightbackground="#2a2d3f",
            )
            progress_canvas.grid(row=2, column=col, padx=6, pady=(0, 8), sticky="nsew")
            self.grid_frame.rowconfigure(2, weight=1)

            progress_canvas.create_rectangle(0, 0, 1, 66, fill="#2bbf6a", outline="", tags="fill")
            progress_canvas.create_text(
                10,
                33,
                text="0/0 clientes",
                fill="white",
                anchor="w",
                font=("Arial", 9, "bold"),
                tags="label",
            )

            self.client_progress_canvases.append(progress_canvas)

    def _draw_client_progress(self, canvas, connected_clients, expected_clients, buyer_threads):
        canvas.update_idletasks()
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())

        canvas.delete("fill")
        canvas.create_rectangle(0, 0, w, h, fill="#5b1d1d", outline="", tags="fill")

        ratio = 0.0
        if expected_clients > 0:
            ratio = min(1.0, connected_clients / expected_clients)

        fill_width = int(w * ratio)
        if fill_width > 0:
            canvas.create_rectangle(0, 0, fill_width, h, fill="#2bbf6a", outline="", tags="fill")

        if 0 < expected_clients <= 80:
            segment_width = w / expected_clients
            for idx in range(1, expected_clients):
                x = int(idx * segment_width)
                canvas.create_line(x, 0, x, h, fill="#2a2d3f", tags="fill")

        canvas.delete("label")
        canvas.create_text(
            8,
            h // 2,
            text=f"{connected_clients}/{expected_clients} clientes · {buyer_threads} hilos",
            fill="white",
            anchor="w",
            font=("Arial", 9, "bold"),
            tags="label",
        )

    def refresh(self):
        snapshot = self.state.get_snapshot()
        expected_servers = snapshot["expected_servers"]
        registered = snapshot["registered_servers"]
        started = snapshot["global_started"]

        if started:
            status_text = "GLOBAL_START enviado. Ventas en curso o finalizadas."
        else:
            status_text = f"Servidores registrados: {registered}/{expected_servers}. Esperando condición global."
        self.status_label.config(text=status_text)

        for slot in snapshot["slots"]:
            idx = slot["slot"]
            sale_id = slot["sale_id"]
            status = slot["status"]
            expected_clients = slot["expected_clients"]
            connected_clients = slot["connected_clients"]
            buyer_threads = slot.get("total_buyer_threads", 0)

            name = f"Servidor {idx + 1}"
            if sale_id:
                name = f"Servidor {idx + 1}\n{sale_id}"
            self.server_name_labels[idx].config(text=name)

            state_text = {
                STATUS_GRAY: "Sin conexión",
                STATUS_BLUE: "Conectado",
                STATUS_ORANGE: "Venta en proceso",
                STATUS_GREEN: "Venta finalizada",
            }.get(status, "Sin conexión")

            self.server_state_cells[idx].config(
                text=state_text,
                bg=STATUS_COLORS.get(status, STATUS_COLORS[STATUS_GRAY]),
            )

            self._draw_client_progress(
                self.client_progress_canvases[idx],
                connected_clients,
                expected_clients,
                buyer_threads,
            )

        self.root.after(120, self.refresh)

    def run(self):
        self.refresh()
        self.root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(description="Coordinador global para múltiples servidores de venta")
    parser.add_argument("expected_servers", type=int, help="Cantidad de servidores de venta a sincronizar")
    parser.add_argument("--host", default="127.0.0.1", help="Host para escuchar conexiones")
    parser.add_argument("--port", type=int, default=6000, help="Puerto para escuchar conexiones")
    parser.add_argument("--no-gui", action="store_true", help="Ejecuta el coordinador sin interfaz visual")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.expected_servers <= 0:
        raise ValueError("expected_servers debe ser mayor que 0")

    state = CoordinatorState(args.expected_servers)
    server = CoordinatorServer((args.host, args.port), CoordinatorHandler, state)

    print("Coordinador global iniciado")
    print(f"Escuchando en {args.host}:{args.port}")
    print(f"Servidores esperados: {args.expected_servers}")

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    if args.no_gui:
        try:
            server_thread.join()
        except KeyboardInterrupt:
            print("\n[Coordinador] Interrupción recibida. Cerrando...")
        finally:
            server.shutdown()
            server.server_close()
        return

    try:
        dashboard = CoordinatorDashboard(state, args.host, args.port)
        dashboard.run()
    except tk.TclError:
        print("[Coordinador] No fue posible iniciar la interfaz. Ejecuta con --no-gui.")
    except KeyboardInterrupt:
        print("\n[Coordinador] Interrupción recibida. Cerrando...")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
