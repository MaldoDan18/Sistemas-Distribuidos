# Ticketing Service - web service para la practica 6

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class TicketStore:
    def __init__(self, store_file: str | Path):
        self.store_file = Path(store_file)
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.ticket_count = self._load_existing_count()

    def _load_existing_count(self) -> int:
        if not self.store_file.exists():
            return 0

        count = 0
        with self.store_file.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                if raw_line.strip():
                    count += 1
        return count

    def list_tickets(self) -> list[dict[str, Any]]:
        tickets: list[dict[str, Any]] = []
        if not self.store_file.exists():
            return tickets

        with self.store_file.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    tickets.append(json.loads(raw_line))
                except json.JSONDecodeError:
                    continue
        return tickets

    def create_ticket(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        required_fields = ["sale_id", "buyer_id", "buyer_type", "zone", "seat", "reservation_id", "request_id"]
        missing_fields = [field for field in required_fields if not payload.get(field)]

        seat = payload.get("seat")
        if not isinstance(seat, dict):
            missing_fields.append("seat")
        elif "row" not in seat or "col" not in seat:
            missing_fields.append("seat.row/seat.col")

        if missing_fields:
            raise ValueError("Faltan campos requeridos: " + ", ".join(missing_fields))

        ticket_id = f"TKT-{uuid.uuid4().hex[:12].upper()}"
        created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        record = {
            "ticket_id": ticket_id,
            "created_at": created_at,
            "sale_id": payload["sale_id"],
            "buyer_id": payload["buyer_id"],
            "buyer_type": payload["buyer_type"],
            "zone": payload["zone"],
            "seat": {
                "row": int(seat["row"]),
                "col": int(seat["col"]),
            },
            "reservation_id": payload["reservation_id"],
            "request_id": payload["request_id"],
            "server_host": payload.get("server_host"),
            "server_port": payload.get("server_port"),
        }

        line = json.dumps(record, ensure_ascii=False)
        with self.lock:
            with self.store_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self.ticket_count += 1
            stored_count = self.ticket_count

        return record, stored_count


class TicketingHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "TicketingServiceHTTP/1.0"

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
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(payload, dict):
            raise ValueError("invalid_json")
        return payload

    @property
    def ticket_store(self) -> TicketStore:
        return self.server.ticket_store  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "ticketing-service",
                    "stored_count": self.ticket_store.ticket_count,
                    "store_file": str(self.ticket_store.store_file),
                },
            )
            return

        if parsed.path == "/tickets":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "tickets": self.ticket_store.list_tickets(),
                    "stored_count": self.ticket_store.ticket_count,
                },
            )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"status": "error", "code": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path != "/tickets":
            self._send_json(HTTPStatus.NOT_FOUND, {"status": "error", "code": "not_found"})
            return

        try:
            payload = self._read_json()
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "error", "code": "invalid_json"})
            return

        try:
            ticket, stored_count = self.ticket_store.create_ticket(payload)
        except ValueError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "status": "error",
                    "code": "invalid_payload",
                    "message": str(exc),
                },
            )
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "status": "error",
                    "code": "storage_failed",
                    "message": f"No fue posible almacenar el ticket: {exc}",
                },
            )
            return

        self._send_json(
            HTTPStatus.CREATED,
            {
                "status": "ok",
                "ticket_id": ticket["ticket_id"],
                "ticket": ticket,
                "store_file": str(self.ticket_store.store_file),
                "stored_count": stored_count,
            },
        )


class TicketingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, ticket_store):
        super().__init__(server_address, RequestHandlerClass)
        self.ticket_store = ticket_store


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ticketing Service web para la practica 6")
    parser.add_argument("--host", default="127.0.0.1", help="Host para escuchar conexiones HTTP")
    parser.add_argument("--port", type=int, default=8001, help="Puerto para escuchar conexiones HTTP")
    parser.add_argument(
        "--store-file",
        default=str(Path(__file__).resolve().parent / "tickets" / "tickets.txt"),
        help="Archivo de almacenamiento de tickets",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ticket_store = TicketStore(args.store_file)
    server = TicketingHTTPServer((args.host, args.port), TicketingHTTPRequestHandler, ticket_store)

    print("Ticketing Service web iniciado")
    print(f"Escuchando en http://{args.host}:{args.port}")
    print(f"Archivo de tickets: {ticket_store.store_file}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Ticketing Service Web] Interrupcion recibida. Cerrando servicio...")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
