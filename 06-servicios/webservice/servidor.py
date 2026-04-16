"""Servidor de venta web para una simulacion rapida.

Expone endpoints HTTP para reservar asientos, confirmar compras y generar
tickets mediante un Ticketing Service tambien expuesto por HTTP.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import tkinter as tk
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

FILAS = 30
COLUMNAS = 50
RESERVA_TTL_SEGUNDOS = 30.0
COMPRA_GRACE_SEGUNDOS = 30.0
TOTAL_ASIENTOS = FILAS * COLUMNAS
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


def build_zone_seats() -> dict[str, list[tuple[int, int]]]:
	zones = {
		ZONA_PLATINO: [],
		ZONA_PREFERENTE: [],
		ZONA_NORMAL: [],
	}

	for row in range(FILAS):
		for col in range(COLUMNAS):
			if row <= 2:
				zones[ZONA_PLATINO].append((row, col))
			elif row <= 6:
				zones[ZONA_PREFERENTE].append((row, col))
			else:
				zones[ZONA_NORMAL].append((row, col))

	return zones


def http_json_request(method: str, url: str, payload: dict[str, Any] | None = None, timeout: float = 4.0) -> dict[str, Any]:
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


class TicketingHTTPClient:
	def __init__(self, base_url: str, timeout: float = 4.0):
		self.base_url = base_url.rstrip("/")
		self.timeout = timeout

	def create_ticket(self, payload: dict[str, Any]) -> dict[str, Any]:
		return http_json_request("POST", f"{self.base_url}/tickets", payload, timeout=self.timeout)


class CoordinatorHTTPClient:
	def __init__(self, base_url: str, timeout: float = 4.0):
		self.base_url = base_url.rstrip("/")
		self.timeout = timeout

	def register_sale(self, payload: dict[str, Any]) -> dict[str, Any]:
		return http_json_request("POST", f"{self.base_url}/sales/register", payload, timeout=self.timeout)

	def close_sale(self, payload: dict[str, Any]) -> dict[str, Any]:
		return http_json_request("POST", f"{self.base_url}/sales/close", payload, timeout=self.timeout)

	def mark_sale_ready(self, payload: dict[str, Any]) -> dict[str, Any]:
		return http_json_request("POST", f"{self.base_url}/sales/ready", payload, timeout=self.timeout)

	def global_start_status(self, sale_id: str) -> dict[str, Any]:
		return http_json_request("GET", f"{self.base_url}/global-start?sale_id={sale_id}", timeout=self.timeout)


class SaleState:
	def __init__(self, sale_id: str, sold_limit: int = TOTAL_ASIENTOS, expected_clients: int = 1):
		self.sale_id = sale_id
		self.sold_limit = sold_limit
		self.expected_clients = max(1, int(expected_clients))
		self.lock = threading.RLock()
		self.zone_seats = build_zone_seats()
		self.reservations: dict[str, dict[str, Any]] = {}
		self.seat_state = [["FREE" for _ in range(COLUMNAS)] for _ in range(FILAS)]
		self.sold_count = 0
		self.reserve_count = 0
		self.purchase_count = 0
		self.purchase_fail_count = 0
		self.expired_reservations = 0
		self.status = "not_started"
		self.close_reason: str | None = None
		self.sales_started_at: float | None = None
		self.sales_finished_at: float | None = None
		self.summary_printed = False
		self.connected_clients = 0
		self.ready_clients = 0
		self.buyers_registered = 0
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
		self.registered_clients: set[str] = set()
		self.ready_client_ids: set[str] = set()
		self.cleanup_stop = threading.Event()
		self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
		self.cleanup_thread.start()

	@staticmethod
	def _normalize_buyer_type(raw_type: str | None) -> str:
		normalized = str(raw_type or "").strip().lower()
		if normalized not in {TIPO_PLATINO, TIPO_PREFERENTE, TIPO_NORMAL}:
			return TIPO_NORMAL
		return normalized

	def _remaining_buyers_locked(self, buyer_type: str) -> int:
		return max(0, self.registered_buyers_by_type[buyer_type] - self.purchased_by_type[buyer_type])

	def _eligible_remaining_for_zone_locked(self, zone: str) -> int:
		remaining_platino = self._remaining_buyers_locked(TIPO_PLATINO)
		remaining_preferente = self._remaining_buyers_locked(TIPO_PREFERENTE)
		remaining_normal = self._remaining_buyers_locked(TIPO_NORMAL)

		if zone == ZONA_PLATINO:
			return remaining_platino
		if zone == ZONA_PREFERENTE:
			return remaining_platino + remaining_preferente
		return remaining_platino + remaining_preferente + remaining_normal

	def _zone_inventory_locked(self, zone: str) -> int:
		free_count = 0
		reserved_count = 0
		for row, col in self.zone_seats[zone]:
			status = self.seat_state[row][col]
			if status == "FREE":
				free_count += 1
			elif status == "RESERVED":
				reserved_count += 1
		return free_count + reserved_count

	def _is_sale_still_possible_locked(self) -> bool:
		for zone in (ZONA_PLATINO, ZONA_PREFERENTE, ZONA_NORMAL):
			if self._zone_inventory_locked(zone) <= 0:
				continue
			if self._eligible_remaining_for_zone_locked(zone) > 0:
				return True
		return False

	def _close_if_unsellable_locked(self) -> bool:
		if self.status in {"closed", "not_started"}:
			return False
		if self.sold_count >= self.sold_limit:
			return False
		if self._is_sale_still_possible_locked():
			return False
		self._close_locked("unsellable_remaining")
		return True

	def register_client(self, client_id: str, buyers_count: int, client_type: str | None = None) -> dict[str, Any]:
		client_id = str(client_id or "").strip()
		if not client_id:
			raise ValueError("client_id es requerido")
		buyer_type = self._normalize_buyer_type(client_type)

		with self.lock:
			if client_id not in self.registered_clients:
				self.registered_clients.add(client_id)
				self.connected_clients += 1
				buyers = max(0, int(buyers_count or 0))
				self.buyers_registered += buyers
				self.registered_buyers_by_type[buyer_type] += buyers
			return {
				"client_id": client_id,
				"connected_clients": self.connected_clients,
				"expected_clients": self.expected_clients,
				"buyers_registered": self.buyers_registered,
			}

	def mark_client_ready(self, client_id: str) -> dict[str, Any]:
		client_id = str(client_id or "").strip()
		if not client_id:
			raise ValueError("client_id es requerido")

		with self.lock:
			if client_id not in self.registered_clients:
				raise ValueError("client_id no registrado")
			if client_id not in self.ready_client_ids:
				self.ready_client_ids.add(client_id)
				self.ready_clients += 1
			return {
				"client_id": client_id,
				"ready_clients": self.ready_clients,
				"expected_clients": self.expected_clients,
				"all_ready": self.ready_clients >= self.expected_clients,
			}

	def start_sales(self, reason: str = "start") -> bool:
		with self.lock:
			if self.status == "closed":
				return False
			if self.status == "open":
				return True
			self.status = "open"
			if self.sales_started_at is None:
				self.sales_started_at = time.perf_counter()
			self.close_reason = reason
			return True

	def all_clients_ready(self) -> bool:
		with self.lock:
			return self.ready_clients >= self.expected_clients

	def _cleanup_loop(self) -> None:
		while not self.cleanup_stop.is_set():
			try:
				self.release_expired_reservations()
			except Exception:
				pass
			self.cleanup_stop.wait(0.25)

	def _buyer_allowed_zones(self, buyer_type: str) -> list[str]:
		normalized = (buyer_type or TIPO_NORMAL).strip().lower()
		return ALLOWED_ZONES_BY_TYPE.get(normalized, [ZONA_NORMAL])

	def _pick_seat(self, buyer_type: str) -> tuple[str, tuple[int, int]] | None:
		for zone in self._buyer_allowed_zones(buyer_type):
			for seat in self.zone_seats[zone]:
				row, col = seat
				if self.seat_state[row][col] == "FREE":
					return zone, seat
		return None

	def _close_locked(self, reason: str) -> None:
		if self.status == "closed":
			return
		self.status = "closed"
		self.close_reason = reason
		self.sales_finished_at = time.perf_counter()
		self.cleanup_stop.set()

	def reserve(self, buyer_id: str, buyer_type: str) -> dict[str, Any]:
		buyer_id = str(buyer_id or "").strip()
		if not buyer_id:
			raise ValueError("buyer_id es requerido")

		with self.lock:
			self.release_expired_reservations_locked()
			self._close_if_unsellable_locked()
			if self.status == "not_started":
				raise RuntimeError("not_started")
			if self.status == "closed":
				raise RuntimeError("sales_closed")
			if self.sold_count >= self.sold_limit:
				self._close_locked("sold_limit_reached")
				raise RuntimeError("sold_limit_reached")

			picked = self._pick_seat(buyer_type)
			if picked is None:
				if self._close_if_unsellable_locked():
					raise RuntimeError("sales_closed")
				raise RuntimeError("no_zone_available")

			zone, seat = picked
			row, col = seat
			reservation_id = str(uuid.uuid4())
			expires_at = time.time() + RESERVA_TTL_SEGUNDOS
			record = {
				"reservation_id": reservation_id,
				"buyer_id": buyer_id,
				"buyer_type": buyer_type,
				"zone": zone,
				"seat": {"row": row, "col": col},
				"created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
				"expires_at": expires_at,
				"in_purchase": False,
			}

			self.seat_state[row][col] = "RESERVED"
			self.reservations[reservation_id] = record
			self.reserve_count += 1
			return record

	def purchase(self, buyer_id: str, reservation_id: str, ticketing_client: TicketingHTTPClient, server_host: str, server_port: int) -> dict[str, Any]:
		buyer_id = str(buyer_id or "").strip()
		reservation_id = str(reservation_id or "").strip()
		if not buyer_id:
			raise ValueError("buyer_id es requerido")
		if not reservation_id:
			raise ValueError("reservation_id es requerido")

		with self.lock:
			self.release_expired_reservations_locked()
			self._close_if_unsellable_locked()
			if self.status == "not_started":
				raise RuntimeError("not_started")
			if self.status == "closed":
				raise RuntimeError("sales_closed")

			reservation = self.reservations.get(reservation_id)
			if reservation is None:
				raise RuntimeError("reservation_not_found")
			if reservation["buyer_id"] != buyer_id:
				raise RuntimeError("reservation_owner_mismatch")
			reservation["in_purchase"] = True
			# Evita que el cleanup expire la reserva mientras se completa el ticketing externo.
			reservation["expires_at"] = time.time() + max(RESERVA_TTL_SEGUNDOS, COMPRA_GRACE_SEGUNDOS)

			row = reservation["seat"]["row"]
			col = reservation["seat"]["col"]
			ticket_payload = {
				"sale_id": self.sale_id,
				"buyer_id": buyer_id,
				"buyer_type": reservation["buyer_type"],
				"zone": reservation["zone"],
				"seat": reservation["seat"],
				"reservation_id": reservation_id,
				"request_id": str(uuid.uuid4()),
				"server_host": server_host,
				"server_port": server_port,
			}

		try:
			ticket_response = ticketing_client.create_ticket(ticket_payload)
		except Exception as exc:
			with self.lock:
				reservation = self.reservations.get(reservation_id)
				if reservation is not None:
					reservation["in_purchase"] = False
					reservation["expires_at"] = time.time() + RESERVA_TTL_SEGUNDOS
				self.purchase_fail_count += 1
			raise RuntimeError(f"ticketing_unreachable: {exc}") from exc

		with self.lock:
			self.release_expired_reservations_locked()
			reservation = self.reservations.get(reservation_id)
			if reservation is None:
				self.purchase_fail_count += 1
				raise RuntimeError("reservation_expired")
			if reservation["buyer_id"] != buyer_id:
				self.purchase_fail_count += 1
				raise RuntimeError("reservation_owner_mismatch")

			if ticket_response.get("status") != "ok" or not ticket_response.get("ticket_id"):
				reservation["in_purchase"] = False
				reservation["expires_at"] = time.time() + RESERVA_TTL_SEGUNDOS
				self.purchase_fail_count += 1
				raise RuntimeError("ticketing_rejected")

			self.reservations.pop(reservation_id, None)
			self.seat_state[row][col] = "SOLD"
			self.sold_count += 1
			self.purchase_count += 1
			buyer_type = self._normalize_buyer_type(str(reservation.get("buyer_type") or ""))
			self.purchased_by_type[buyer_type] += 1

			if self.sold_count >= self.sold_limit:
				self._close_locked("sold_limit_reached")
			else:
				self._close_if_unsellable_locked()

			return {
				"reservation": reservation,
				"ticket": ticket_response.get("ticket"),
				"ticket_id": ticket_response.get("ticket_id"),
				"stored_count": ticket_response.get("stored_count"),
				"sold_count": self.sold_count,
			}

	def release_expired_reservations_locked(self) -> int:
		now = time.time()
		released = 0
		for reservation_id, record in list(self.reservations.items()):
			if record.get("in_purchase"):
				continue
			if record["expires_at"] > now:
				continue
			row = record["seat"]["row"]
			col = record["seat"]["col"]
			self.seat_state[row][col] = "FREE"
			self.reservations.pop(reservation_id, None)
			released += 1
		self.expired_reservations += released
		self._close_if_unsellable_locked()
		return released

	def release_expired_reservations(self) -> int:
		with self.lock:
			return self.release_expired_reservations_locked()

	def summary(self) -> dict[str, Any]:
		with self.lock:
			total_elapsed = None
			if self.sales_started_at is not None and self.sales_finished_at is not None:
				total_elapsed = self.sales_finished_at - self.sales_started_at
			reserved_count = len(self.reservations)
			free_count = (FILAS * COLUMNAS) - self.sold_count - reserved_count
			return {
				"sale_id": self.sale_id,
				"status": self.status,
				"close_reason": self.close_reason,
				"sold_count": self.sold_count,
				"sold_limit": self.sold_limit,
				"sales_open": self.status == "open",
				"connected_clients": self.connected_clients,
				"ready_clients": self.ready_clients,
				"expected_clients": self.expected_clients,
				"buyers_registered": self.buyers_registered,
				"active_reservations": reserved_count,
				"free_count": free_count,
				"reserve_count": self.reserve_count,
				"purchase_count": self.purchase_count,
				"purchase_fail_count": self.purchase_fail_count,
				"expired_reservations": self.expired_reservations,
				"elapsed": total_elapsed,
			}

	def print_summary_once(self) -> None:
		with self.lock:
			if self.summary_printed:
				return
			self.summary_printed = True
		self.print_summary()

	def print_summary(self) -> None:
		with self.lock:
			if self.sales_started_at is None:
				total_elapsed = 0.0
			elif self.sales_finished_at is None:
				total_elapsed = time.perf_counter() - self.sales_started_at
			else:
				total_elapsed = self.sales_finished_at - self.sales_started_at

			reserved_count = len(self.reservations)
			free_count = (FILAS * COLUMNAS) - self.sold_count - reserved_count
			reserve_avg = (total_elapsed / self.reserve_count) if self.reserve_count > 0 else 0.0
			purchase_avg = (total_elapsed / self.purchase_count) if self.purchase_count > 0 else 0.0

			print("\n========== Resumen del Servidor Web ==========")
			print(f"Venta: {self.sale_id}")
			print(f"Estado final: {self.status}")
			print(f"Motivo de cierre: {self.close_reason}")
			print(f"Asientos vendidos: {self.sold_count}/{self.sold_limit}")
			print(f"Asientos apartados al cierre: {reserved_count}")
			print(f"Asientos libres al cierre: {free_count}")
			print(f"Clientes conectados: {self.connected_clients}/{self.expected_clients}")
			print(f"Clientes listos: {self.ready_clients}/{self.expected_clients}")
			print(f"Hilos compradores registrados: {self.buyers_registered}")
			print(f"Solicitudes de reserva: {self.reserve_count}")
			print(f"Compras exitosas: {self.purchase_count}")
			print(f"Compras fallidas: {self.purchase_fail_count}")
			print(f"Reservas expiradas liberadas: {self.expired_reservations}")
			print(f"Tiempo total de venta: {total_elapsed:.4f} s")
			print(f"Tiempo promedio por reserva (estimado): {reserve_avg:.6f} s")
			print(f"Tiempo promedio por compra (estimado): {purchase_avg:.6f} s")
			print("=============================================\n")

	def seat_matrix_snapshot(self) -> list[list[str]]:
		with self.lock:
			return [row[:] for row in self.seat_state]


class SaleDashboard:
	"""GUI del servidor web con secciones visuales iguales al modelo TCP."""

	def __init__(self, state: SaleState, host: str, port: int, ticketing_url: str):
		self.state = state
		self.root = tk.Tk()
		self.root.title(f"Servidor Web - {state.sale_id} ({host}:{port})")
		self.root.configure(bg="#0a0e27")

		self.label_margin = 30
		self.cell_size = 18
		self.grid_width = COLUMNAS * self.cell_size
		self.visual_rows = FILAS + (SECTION_GAP_ROWS * 2) + (SECTION_LABEL_ROWS * 3)
		self.grid_height = self.visual_rows * self.cell_size
		self.canvas_width = self.label_margin + self.grid_width + 10
		self.canvas_height = self.label_margin + self.grid_height + 10

		tk.Label(
			self.root,
			text=f"Venta {state.sale_id} | Ticketing: {ticketing_url}",
			font=("Arial", 12, "bold"),
			fg="#276ef1",
			bg="#0a0e27",
		).pack(pady=(8, 6))

		self.status_var = tk.StringVar(value="Estado: open")
		self.metrics_var = tk.StringVar(value="")

		tk.Label(self.root, textvariable=self.status_var, font=("Consolas", 10), fg="#e8eefc", bg="#0a0e27").pack()
		tk.Label(self.root, textvariable=self.metrics_var, font=("Consolas", 10), fg="#d8dbe7", bg="#0a0e27").pack(pady=(0, 8))

		self.main_frame = tk.Frame(self.root, bg="white")
		self.main_frame.pack(padx=10, pady=10)

		self.canvas = tk.Canvas(self.main_frame, width=self.canvas_width, height=self.canvas_height, bg="white")
		self.canvas.pack(side="left")

		info_frame = tk.Frame(self.main_frame, padx=16, bg="white")
		info_frame.pack(side="left", fill="y")

		tk.Label(info_frame, text=f"Servidor: {host}:{port}", font=("Arial", 11), anchor="w", background="white").pack(fill="x", pady=(4, 8))
		self.sold_label = tk.Label(info_frame, text="Asientos vendidos: 0", font=("Arial", 11), anchor="w", bg="white")
		self.sold_label.pack(fill="x", pady=4)
		self.reserved_label = tk.Label(info_frame, text="Asientos apartados: 0", font=("Arial", 11), anchor="w", bg="white")
		self.reserved_label.pack(fill="x", pady=4)
		self.free_label = tk.Label(info_frame, text=f"Asientos libres: {TOTAL_ASIENTOS}", font=("Arial", 11), anchor="w", bg="white")
		self.free_label.pack(fill="x", pady=4)

		tk.Label(info_frame, text="Leyenda", font=("Arial", 11, "bold"), anchor="w", background="white").pack(fill="x", pady=(14, 4))
		tk.Label(info_frame, text="Color zona: Libre", font=("Arial", 10), anchor="w", background="white").pack(fill="x")
		tk.Label(info_frame, text="Naranja: Apartado", font=("Arial", 10), anchor="w", background="white").pack(fill="x")
		tk.Label(info_frame, text="Azul: Vendido", font=("Arial", 10), anchor="w", background="white").pack(fill="x")

		tk.Label(info_frame, text="Secciones", font=("Arial", 11, "bold"), anchor="w", background="white").pack(fill="x", pady=(14, 4))
		tk.Label(info_frame, text="Platino: filas 1-3", font=("Arial", 10), anchor="w", background="white").pack(fill="x")
		tk.Label(info_frame, text="Preferente: filas 4-7", font=("Arial", 10), anchor="w", background="white").pack(fill="x")
		tk.Label(info_frame, text="Normal: filas 8-30", font=("Arial", 10), anchor="w", background="white").pack(fill="x")

		self.radius = int(self.cell_size * 0.35)
		self.seat_items = [[None for _ in range(COLUMNAS)] for _ in range(FILAS)]
		self.last_status = [[None for _ in range(COLUMNAS)] for _ in range(FILAS)]

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
	def zone_for_row(row: int) -> str:
		if row <= 2:
			return ZONA_PLATINO
		if row <= 6:
			return ZONA_PREFERENTE
		return ZONA_NORMAL

	@staticmethod
	def free_color_for_row(row: int) -> str:
		zone = SaleDashboard.zone_for_row(row)
		if zone == ZONA_PLATINO:
			return "#B87474"
		if zone == ZONA_PREFERENTE:
			return "#73B27D"
		return "gray"

	def _to_visual_row(self, row: int) -> int:
		offset = SECTION_LABEL_ROWS
		if row >= 3:
			offset += SECTION_GAP_ROWS + SECTION_LABEL_ROWS
		if row >= 7:
			offset += SECTION_GAP_ROWS + SECTION_LABEL_ROWS
		return row + offset

	def _draw_zone_guides(self) -> None:
		pref_end_visual_row = self._to_visual_row(2) + 1
		plat_end_visual_row = self._to_visual_row(6) + 1

		y_pref_end = self.label_margin + (pref_end_visual_row * self.cell_size)
		y_plat_end = self.label_margin + (plat_end_visual_row * self.cell_size)

		self.canvas.create_line(self.label_margin, y_pref_end, self.label_margin + self.grid_width, y_pref_end, fill="#9A9A9A", dash=(3, 2))
		self.canvas.create_line(self.label_margin, y_plat_end, self.label_margin + self.grid_width, y_plat_end, fill="#9A9A9A", dash=(3, 2))

	def _draw_section_labels(self) -> None:
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
	def seat_color(status: str, row: int) -> str:
		if status == "SOLD":
			return "blue"
		if status == "RESERVED":
			return "orange"
		return SaleDashboard.free_color_for_row(row)

	def _refresh(self) -> None:
		summary = self.state.summary()
		matrix = self.state.seat_matrix_snapshot()
		if summary.get("status") == "closed":
			self.state.print_summary_once()

		self.status_var.set(f"Estado: {summary['status']} | Motivo cierre: {summary.get('close_reason') or '-'}")
		elapsed = summary.get("elapsed")
		elapsed_text = "-" if elapsed is None else f"{elapsed:.3f}s"
		self.metrics_var.set(
			f"Reserve req: {summary['reserve_count']} | Purchase ok: {summary['purchase_count']} | "
			f"Purchase fail: {summary['purchase_fail_count']} | Expired: {summary['expired_reservations']} | Elapsed: {elapsed_text}"
		)

		for r in range(FILAS):
			for c in range(COLUMNAS):
				current = matrix[r][c]
				if self.last_status[r][c] != current:
					self.last_status[r][c] = current
					self.canvas.itemconfig(self.seat_items[r][c], fill=self.seat_color(current, r))

		self.sold_label.config(text=f"Asientos vendidos: {summary['sold_count']}")
		self.reserved_label.config(text=f"Asientos apartados: {summary['active_reservations']}")
		self.free_label.config(text=f"Asientos libres: {summary['free_count']}")

		self.root.after(120, self._refresh)

	def run(self) -> None:
		self.root.after(150, self._refresh)
		self.root.mainloop()


class SaleHTTPServer(ThreadingHTTPServer):
	allow_reuse_address = True
	daemon_threads = True

	def __init__(self, server_address, RequestHandlerClass, sale_state, ticketing_client, coordinator_client=None, coordinator_enabled=False):
		super().__init__(server_address, RequestHandlerClass)
		self.sale_state = sale_state
		self.ticketing_client = ticketing_client
		self.coordinator_client = coordinator_client
		self.coordinator_enabled = coordinator_enabled
		self.coordinator_ready_sent = False


class SaleHTTPRequestHandler(BaseHTTPRequestHandler):
	server_version = "SaleWebService/1.0"

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
	def state(self) -> SaleState:
		return self.server.sale_state  # type: ignore[attr-defined]

	@property
	def ticketing_client(self) -> TicketingHTTPClient:
		return self.server.ticketing_client  # type: ignore[attr-defined]

	def _maybe_activate_global_start(self) -> None:
		if not self.server.coordinator_enabled or self.server.coordinator_client is None:
			if self.state.all_clients_ready():
				self.state.start_sales("local_ready")
			return

		if not self.state.all_clients_ready():
			return

		if not self.server.coordinator_ready_sent:
			try:
				self.server.coordinator_client.mark_sale_ready({"sale_id": self.state.sale_id})
				self.server.coordinator_ready_sent = True
			except Exception:
				return

		try:
			response = self.server.coordinator_client.global_start_status(self.state.sale_id)
		except Exception:
			return

		if response.get("global_start"):
			self.state.start_sales("global_start")

	def do_GET(self) -> None:  # noqa: N802
		parsed = urlparse(self.path)
		if parsed.path == "/start":
			self._maybe_activate_global_start()
			summary = self.state.summary()
			self._send_json(
				HTTPStatus.OK,
				{
					"status": "ok",
					"started": bool(summary.get("sales_open")),
					"connected_clients": summary.get("connected_clients"),
					"ready_clients": summary.get("ready_clients"),
					"expected_clients": summary.get("expected_clients"),
				},
			)
			return

		if parsed.path == "/health":
			self._maybe_activate_global_start()
			self._send_json(HTTPStatus.OK, {"status": "ok", "service": "sale-web-service", **self.state.summary()})
			return

		if parsed.path == "/state":
			self._send_json(HTTPStatus.OK, self.state.summary())
			return

		self._send_json(HTTPStatus.NOT_FOUND, {"status": "error", "code": "not_found"})

	def do_POST(self) -> None:  # noqa: N802
		parsed = urlparse(self.path)

		try:
			payload = self._read_json()
		except (json.JSONDecodeError, ValueError):
			self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_json"})
			return

		if parsed.path == "/reserve":
			self._handle_reserve(payload)
			return

		if parsed.path == "/register":
			self._handle_register(payload)
			return

		if parsed.path == "/ready":
			self._handle_ready(payload)
			return

		if parsed.path == "/purchase":
			self._handle_purchase(payload)
			return

		if parsed.path == "/close":
			self._handle_close(payload)
			return

		self._send_json(HTTPStatus.NOT_FOUND, {"status": "error", "code": "not_found"})

	def _handle_reserve(self, payload: dict[str, Any]) -> None:
		self._maybe_activate_global_start()
		try:
			reservation = self.state.reserve(payload.get("buyer_id"), payload.get("buyer_type", TIPO_NORMAL))
		except ValueError as exc:
			self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_payload", "message": str(exc)})
			return
		except RuntimeError as exc:
			code = str(exc)
			if code == "not_started":
				self._send_json(HTTPStatus.OK, {"status": "not_started", "message": "La venta aun no inicia."})
				return
			if code == "sales_closed":
				self._send_json(HTTPStatus.OK, {"status": "closed", "message": "La venta fue cerrada."})
				return
			if code in {"sold_out", "sold_limit_reached"}:
				self._send_json(HTTPStatus.OK, {"status": "sold_out", "message": "No hay asientos disponibles."})
				return
			if code == "no_zone_available":
				self._send_json(HTTPStatus.OK, {"status": "error", "code": "no_zone_available"})
				return
			self._send_json(HTTPStatus.OK, {"status": "error", "code": code})
			return

		summary = self.state.summary()
		self._send_json(
			HTTPStatus.OK,
			{
				"status": "ok",
				"reservation_id": reservation["reservation_id"],
				"zone": reservation["zone"],
				"seat": reservation["seat"],
				"expires_at": reservation["expires_at"],
				"remaining": summary["free_count"],
				"reservation": reservation,
			},
		)

	def _handle_register(self, payload: dict[str, Any]) -> None:
		try:
			result = self.state.register_client(
				payload.get("client_id"),
				int(payload.get("buyers") or 0),
				payload.get("client_type"),
			)
		except ValueError as exc:
			self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_payload", "message": str(exc)})
			return

		self._send_json(HTTPStatus.OK, {"status": "ok", **result})

	def _handle_ready(self, payload: dict[str, Any]) -> None:
		try:
			result = self.state.mark_client_ready(payload.get("client_id"))
		except ValueError as exc:
			self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_payload", "message": str(exc)})
			return

		self._maybe_activate_global_start()
		summary = self.state.summary()
		self._send_json(
			HTTPStatus.OK,
			{
				"status": "ok",
				**result,
				"started": bool(summary.get("sales_open")),
			},
		)

	def _handle_purchase(self, payload: dict[str, Any]) -> None:
		self._maybe_activate_global_start()
		try:
			response = self.state.purchase(
				payload.get("buyer_id"),
				payload.get("reservation_id"),
				self.ticketing_client,
				self.server.server_address[0],
				self.server.server_address[1],
			)
		except ValueError as exc:
			self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_payload", "message": str(exc)})
			return
		except RuntimeError as exc:
			code = str(exc)
			if code == "not_started":
				self._send_json(HTTPStatus.OK, {"status": "not_started", "message": "La venta aun no inicia."})
				return
			if code == "sales_closed":
				self._send_json(HTTPStatus.OK, {"status": "closed", "message": "La venta fue cerrada."})
				return
			if code in {"sold_out", "sold_limit_reached"}:
				self._send_json(HTTPStatus.OK, {"status": "sold_out", "message": "No hay asientos disponibles."})
				return
			self._send_json(HTTPStatus.OK, {"status": "error", "code": code})
			return
		except Exception as exc:
			self._send_json(
				HTTPStatus.BAD_GATEWAY,
				{"status": "error", "code": "ticketing_unreachable", "message": str(exc)},
			)
			return

		if self.server.coordinator_enabled and self.server.coordinator_client is not None:
			try:
				self.server.coordinator_client.register_sale({"sale_id": self.state.sale_id, "event": "purchase", "ticket_id": response.get("ticket_id")})
			except Exception:
				pass

		summary = self.state.summary()
		self._send_json(
			HTTPStatus.OK,
			{
				"status": "ok",
				**response,
				"remaining": summary["free_count"],
				"sold_count": summary["sold_count"],
			},
		)

	def _handle_close(self, payload: dict[str, Any]) -> None:
		reason = str(payload.get("reason") or "manual_close")
		with self.state.lock:
			self.state._close_locked(reason)
		self.state.print_summary_once()
		if self.server.coordinator_enabled and self.server.coordinator_client is not None:
			try:
				self.server.coordinator_client.close_sale({"sale_id": self.state.sale_id, "reason": reason})
			except Exception:
				pass
		self._send_json(HTTPStatus.OK, {"status": "ok", **self.state.summary()})


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Servidor de venta web para la practica 6")
	parser.add_argument("--host", default="127.0.0.1", help="Host para escuchar conexiones HTTP")
	parser.add_argument("--port", type=int, default=8080, help="Puerto del servidor HTTP")
	parser.add_argument("--sale-id", default="venta-web", help="Identificador de la venta")
	parser.add_argument("--clients", type=int, default=1, help="Clientes esperados para iniciar la venta")
	parser.add_argument("--sold-limit", type=int, default=TOTAL_ASIENTOS, help="Limite de boletos vendidos")
	parser.add_argument("--ticketing-url", default="http://127.0.0.1:8001", help="URL base del Ticketing Service web")
	parser.add_argument("--coordinator-url", default=None, help="URL base del coordinador web")
	parser.add_argument("--no-gui", action="store_true", help="Ejecuta sin interfaz grafica")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	sale_state = SaleState(args.sale_id, sold_limit=args.sold_limit, expected_clients=args.clients)
	ticketing_client = TicketingHTTPClient(args.ticketing_url)
	coordinator_client = CoordinatorHTTPClient(args.coordinator_url) if args.coordinator_url else None
	server = SaleHTTPServer(
		(args.host, args.port),
		SaleHTTPRequestHandler,
		sale_state,
		ticketing_client,
		coordinator_client=coordinator_client,
		coordinator_enabled=bool(coordinator_client),
	)

	if coordinator_client is not None:
		try:
			coordinator_client.register_sale(
				{
					"sale_id": args.sale_id,
					"server_host": args.host,
					"server_port": args.port,
					"ticketing_url": args.ticketing_url,
					"expected_clients": args.clients,
				}
			)
		except Exception:
			pass

	print("Servidor de venta web iniciado")
	print(f"Escuchando en http://{args.host}:{args.port}")
	print(f"Sale ID: {args.sale_id}")
	print(f"Ticketing Service: {args.ticketing_url}")
	if args.coordinator_url:
		print(f"Coordinador: {args.coordinator_url}")
	print(f"GUI: {'deshabilitada' if args.no_gui else 'habilitada'}")

	server_thread: threading.Thread | None = None

	try:
		if args.no_gui:
			server.serve_forever()
		else:
			server_thread = threading.Thread(target=server.serve_forever, daemon=True)
			server_thread.start()
			dashboard = SaleDashboard(sale_state, args.host, args.port, args.ticketing_url)
			dashboard.run()
	except KeyboardInterrupt:
		print("\n[Servidor Web] Interrupcion recibida. Cerrando servidor...")
	finally:
		with sale_state.lock:
			sale_state._close_locked("shutdown")
		sale_state.print_summary_once()
		if coordinator_client is not None:
			try:
				coordinator_client.close_sale({"sale_id": args.sale_id, "reason": "shutdown"})
			except Exception:
				pass
		server.shutdown()
		server.server_close()
		if server_thread is not None and server_thread.is_alive():
			server_thread.join(timeout=1.0)


if __name__ == "__main__":
	main()
