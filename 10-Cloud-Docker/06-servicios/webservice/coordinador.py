# Coordinador web para la practica 6

from __future__ import annotations

import argparse
import json
import threading
import tkinter as tk
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


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
    def __init__(self, expected_sales: int):
        self.lock = threading.Lock()
        self.expected_sales = max(1, int(expected_sales))
        self.sales: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.global_start_active = False

    def _ensure_sale(self, sale_id: str) -> dict[str, Any]:
        sale = self.sales.setdefault(
            sale_id,
            {
                "sale_id": sale_id,
                "server_host": None,
                "server_port": None,
                "ticketing_url": None,
                "status": "registered",
                "clients_connected": 0,
                "clients_done": 0,
                "buyers_total": 0,
                "expected_clients": 1,
                "ready_for_global_start": False,
                "global_start": False,
                "last_event": None,
            },
        )
        return sale

    def _recompute_global_start_locked(self) -> None:
        if self.global_start_active:
            return
        if len(self.sales) < self.expected_sales:
            return

        for sale in self.sales.values():
            if not sale.get("ready_for_global_start"):
                return

        self.global_start_active = True
        for sale in self.sales.values():
            sale["global_start"] = True
            sale["status"] = "started"
            sale["last_event"] = "global_start"
        self.events.append({"type": "global_start", "sales": list(self.sales.keys())})

    def register_sale(self, payload: dict[str, Any]) -> dict[str, Any]:
        sale_id = str(payload.get("sale_id") or "").strip()
        if not sale_id:
            raise ValueError("sale_id es requerido")

        with self.lock:
            sale = self._ensure_sale(sale_id)
            sale["server_host"] = payload.get("server_host", sale.get("server_host"))
            sale["server_port"] = payload.get("server_port", sale.get("server_port"))
            sale["ticketing_url"] = payload.get("ticketing_url", sale.get("ticketing_url"))
            sale["expected_clients"] = int(payload.get("expected_clients") or sale.get("expected_clients") or 1)
            if not sale.get("global_start"):
                sale["status"] = payload.get("status", sale["status"])
            sale["last_event"] = "sale_registered"
            self.events.append({"type": "sale_registered", "sale_id": sale_id})
            return sale

    def mark_sale_ready(self, payload: dict[str, Any]) -> dict[str, Any]:
        sale_id = str(payload.get("sale_id") or "").strip()
        if not sale_id:
            raise ValueError("sale_id es requerido")

        with self.lock:
            sale = self._ensure_sale(sale_id)
            sale["ready_for_global_start"] = True
            sale["status"] = "ready"
            sale["last_event"] = "sale_ready"
            self.events.append({"type": "sale_ready", "sale_id": sale_id})
            self._recompute_global_start_locked()
            return sale

    def global_start_status(self, sale_id: str) -> dict[str, Any]:
        sale_id = str(sale_id or "").strip()
        if not sale_id:
            raise ValueError("sale_id es requerido")

        with self.lock:
            sale = self._ensure_sale(sale_id)
            self._recompute_global_start_locked()
            return {
                "status": "ok",
                "sale_id": sale_id,
                "global_start": bool(sale.get("global_start")),
                "ready_for_global_start": bool(sale.get("ready_for_global_start")),
                "registered_sales": len(self.sales),
                "expected_sales": self.expected_sales,
            }

    def connect_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        sale_id = str(payload.get("sale_id") or "").strip()
        client_id = str(payload.get("client_id") or "").strip()
        buyers = int(payload.get("buyers") or 0)
        if not sale_id:
            raise ValueError("sale_id es requerido")
        if not client_id:
            raise ValueError("client_id es requerido")

        with self.lock:
            sale = self._ensure_sale(sale_id)
            sale["clients_connected"] += 1
            sale["buyers_total"] += max(0, buyers)
            sale["last_event"] = "client_connected"
            self.events.append({"type": "client_connected", "sale_id": sale_id, "client_id": client_id, "buyers": buyers})
            return sale

    def client_done(self, payload: dict[str, Any]) -> dict[str, Any]:
        sale_id = str(payload.get("sale_id") or "").strip()
        client_id = str(payload.get("client_id") or "").strip()
        if not sale_id:
            raise ValueError("sale_id es requerido")
        if not client_id:
            raise ValueError("client_id es requerido")

        with self.lock:
            sale = self._ensure_sale(sale_id)
            sale["clients_done"] += 1
            sale["last_event"] = "client_done"
            self.events.append({"type": "client_done", "sale_id": sale_id, "client_id": client_id})
            return sale

    def close_sale(self, payload: dict[str, Any]) -> dict[str, Any]:
        sale_id = str(payload.get("sale_id") or "").strip()
        reason = str(payload.get("reason") or "closed")
        if not sale_id:
            raise ValueError("sale_id es requerido")

        with self.lock:
            sale = self._ensure_sale(sale_id)
            sale["status"] = "closed"
            sale["reason"] = reason
            sale["last_event"] = "sale_closed"
            self.events.append({"type": "sale_closed", "sale_id": sale_id, "reason": reason})
            return sale

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            ready_sales = sum(1 for sale in self.sales.values() if sale.get("ready_for_global_start"))
            return {
                "status": "ok",
                "expected_sales": self.expected_sales,
                "registered_sales": len(self.sales),
                "ready_sales": ready_sales,
                "global_start_active": self.global_start_active,
                "sales": list(self.sales.values()),
                "events": list(self.events),
            }


class CoordinatorDashboard:
    """GUI del coordinador con estilo TCP + panel lateral de detalle."""

    def __init__(self, state: CoordinatorState, host: str, port: int):
        self.state = state
        self.root = tk.Tk()
        self.root.title(f"Coordinador global de ventas (Web) - {host}:{port}")
        self.root.geometry("1280x760")
        self.root.configure(bg="#0f1420")

        header = tk.Label(
            self.root,
            text="Coordinador global de ventas",
            font=("Segoe UI", 13, "bold"),
            fg="#e8eefc",
            bg="#0f1420",
        )
        header.pack(pady=(10, 8))

        self.summary_var = tk.StringVar(value="Esperando servidores...")
        summary_label = tk.Label(
            self.root,
            textvariable=self.summary_var,
            font=("Consolas", 10),
            fg="#9ad0ff",
            bg="#0f1420",
        )
        summary_label.pack(pady=(0, 10))

        body = tk.Frame(self.root, bg="#0f1420")
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        left = tk.Frame(body, bg="#0f1420")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = tk.Frame(body, bg="#0f1420")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(10, 0))

        self.grid_frame = tk.Frame(left, bg="#0f1420")
        self.grid_frame.pack(fill=tk.BOTH, expand=True)

        self.server_name_labels: list[tk.Label] = []
        self.server_state_cells: list[tk.Label] = []
        self.client_progress_canvases: list[tk.Canvas] = []
        self._build_grid()

        tk.Label(right, text="Ventas", font=("Segoe UI", 11, "bold"), fg="#d8dbe7", bg="#0f1420").pack(anchor="w")
        self.sales_text = tk.Text(
            right,
            height=17,
            width=58,
            bg="#131b2a",
            fg="#d8dbe7",
            insertbackground="#d8dbe7",
            font=("Consolas", 10),
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.sales_text.pack(fill=tk.BOTH, expand=True, pady=(6, 10))

        tk.Label(right, text="Eventos Recientes", font=("Segoe UI", 11, "bold"), fg="#d8dbe7", bg="#0f1420").pack(anchor="w")
        self.events_text = tk.Text(
            right,
            height=15,
            width=58,
            bg="#131b2a",
            fg="#d8dbe7",
            insertbackground="#d8dbe7",
            font=("Consolas", 10),
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.events_text.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

    def _build_grid(self) -> None:
        total = self.state.expected_sales
        for col in range(total):
            self.grid_frame.columnconfigure(col, weight=1, uniform="sale-col")

            title = tk.Label(
                self.grid_frame,
                text=f"Servidor {col + 1}",
                bg="#0f1420",
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

    @staticmethod
    def _status_to_slot_color(status: str) -> str:
        mapping = {
            "registered": STATUS_BLUE,
            "ready": STATUS_BLUE,
            "started": STATUS_ORANGE,
            "closed": STATUS_GREEN,
        }
        return STATUS_COLORS.get(mapping.get(status, STATUS_GRAY), STATUS_COLORS[STATUS_GRAY])

    @staticmethod
    def _status_to_text(status: str, connected_clients: int, expected_clients: int) -> str:
        if status == "closed":
            return "Finalizado"
        if status == "started":
            return "Venta en proceso"
        if status in {"registered", "ready"}:
            if expected_clients > 0 and connected_clients < expected_clients:
                return "Esperando clientes"
            return "Conectado"
        return "Sin conexión"

    def _draw_client_progress(self, canvas: tk.Canvas, connected_clients: int, expected_clients: int, buyer_threads: int) -> None:
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

    def _render_sales(self, sales: list[dict[str, Any]]) -> None:
        self.sales_text.config(state=tk.NORMAL)
        self.sales_text.delete("1.0", tk.END)

        if not sales:
            self.sales_text.insert(tk.END, "No hay ventas registradas.\n")
        else:
            for sale in sales:
                line = (
                    f"sale_id={sale.get('sale_id')} | status={sale.get('status')} | "
                    f"server={sale.get('server_host')}:{sale.get('server_port')} | "
                    f"clientes={sale.get('clients_connected')} | done={sale.get('clients_done')} | "
                    f"buyers={sale.get('buyers_total')} | last={sale.get('last_event')}"
                )
                self.sales_text.insert(tk.END, line + "\n")

        self.sales_text.config(state=tk.DISABLED)

    def _render_events(self, events: list[dict[str, Any]]) -> None:
        self.events_text.config(state=tk.NORMAL)
        self.events_text.delete("1.0", tk.END)

        if not events:
            self.events_text.insert(tk.END, "Sin eventos.\n")
        else:
            for event in events[-30:]:
                self.events_text.insert(tk.END, json.dumps(event, ensure_ascii=False) + "\n")

        self.events_text.config(state=tk.DISABLED)

    def _refresh(self) -> None:
        snapshot = self.state.snapshot()
        sales = snapshot.get("sales", [])
        events = snapshot.get("events", [])

        expected_sales = int(snapshot.get("expected_sales") or 0)
        registered_sales = int(snapshot.get("registered_sales") or 0)
        ready_sales = int(snapshot.get("ready_sales") or 0)
        started = bool(snapshot.get("global_start_active"))

        if started:
            status_text = "GLOBAL_START enviado. Ventas en curso o finalizadas."
        else:
            status_text = f"Servidores registrados: {registered_sales}/{expected_sales}. Esperando condición global."

        self.summary_var.set(
            f"{status_text} | eventos: {len(events)}"
        )

        sales_by_id = {sale.get("sale_id"): sale for sale in sales if sale.get("sale_id")}
        ordered_sales = sorted(sales_by_id.values(), key=lambda item: str(item.get("sale_id")))

        for idx in range(self.state.expected_sales):
            if idx < len(ordered_sales):
                sale = ordered_sales[idx]
                sale_id = str(sale.get("sale_id"))
                status = str(sale.get("status") or "registered")
                connected_clients = int(sale.get("clients_connected") or 0)
                expected_clients = int(sale.get("expected_clients") or 0)
                buyers = int(sale.get("buyers_total") or 0)

                self.server_name_labels[idx].config(text=f"Servidor {idx + 1}\n{sale_id}")
                self.server_state_cells[idx].config(
                    text=self._status_to_text(status, connected_clients, expected_clients),
                    bg=self._status_to_slot_color(status),
                )
                self._draw_client_progress(
                    self.client_progress_canvases[idx],
                    connected_clients,
                    expected_clients,
                    buyers,
                )
            else:
                self.server_name_labels[idx].config(text=f"Servidor {idx + 1}")
                self.server_state_cells[idx].config(text="Sin conexión", bg=STATUS_COLORS[STATUS_GRAY])
                self._draw_client_progress(self.client_progress_canvases[idx], 0, 0, 0)

        self._render_sales(sales)
        self._render_events(events)
        self.root.after(300, self._refresh)

    def run(self) -> None:
        self.root.after(150, self._refresh)
        self.root.mainloop()


class CoordinatorHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "CoordinatorWeb/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw_body:
            return {}
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid_json")
        return payload

    @property
    def state(self) -> CoordinatorState:
        return self.server.coordinator_state  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok", "service": "coordinator-web"})
            return

        if parsed.path == "/state":
            self._send_json(HTTPStatus.OK, self.state.snapshot())
            return

        if parsed.path == "/global-start":
            query = parse_qs(parsed.query)
            sale_id = (query.get("sale_id") or [""])[0]
            try:
                response = self.state.global_start_status(sale_id)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_payload", "message": str(exc)})
                return
            self._send_json(HTTPStatus.OK, response)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"status": "error", "code": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        try:
            payload = self._read_json()
        except (json.JSONDecodeError, ValueError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_json"})
            return

        try:
            if parsed.path == "/sales/register":
                result = self.state.register_sale(payload)
            elif parsed.path == "/sales/ready":
                result = self.state.mark_sale_ready(payload)
            elif parsed.path == "/clients/connect":
                result = self.state.connect_client(payload)
            elif parsed.path == "/clients/done":
                result = self.state.client_done(payload)
            elif parsed.path == "/sales/close":
                result = self.state.close_sale(payload)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"status": "error", "code": "not_found"})
                return
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_payload", "message": str(exc)})
            return

        self._send_json(HTTPStatus.OK, {"status": "ok", "sale": result})


class CoordinatorHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, coordinator_state):
        super().__init__(server_address, RequestHandlerClass)
        self.coordinator_state = coordinator_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coordinador web para la practica 6")
    parser.add_argument("--host", default="127.0.0.1", help="Host para escuchar conexiones HTTP")
    parser.add_argument("--port", type=int, default=8090, help="Puerto del coordinador HTTP")
    parser.add_argument("--sales", type=int, default=1, help="Cantidad esperada de ventas/servidores")
    parser.add_argument("--no-gui", action="store_true", help="Ejecuta sin interfaz grafica")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    coordinator_state = CoordinatorState(args.sales)
    server = CoordinatorHTTPServer((args.host, args.port), CoordinatorHTTPRequestHandler, coordinator_state)

    print("Coordinador web iniciado")
    print(f"Escuchando en http://{args.host}:{args.port}")
    print(f"GUI: {'deshabilitada' if args.no_gui else 'habilitada'}")

    server_thread: threading.Thread | None = None
    try:
        if args.no_gui:
            server.serve_forever()
        else:
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            dashboard = CoordinatorDashboard(coordinator_state, args.host, args.port)
            dashboard.run()
    except KeyboardInterrupt:
        print("\n[Coordinador Web] Interrupcion recibida. Cerrando coordinador...")
    finally:
        server.shutdown()
        server.server_close()
        if server_thread is not None and server_thread.is_alive():
            server_thread.join(timeout=1.0)


if __name__ == "__main__":
    main()
