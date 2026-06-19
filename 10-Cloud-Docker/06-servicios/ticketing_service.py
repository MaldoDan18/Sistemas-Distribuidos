# Practica 6 - Ticketing Service

import argparse
import json
import socketserver
import threading
import time
import uuid
from pathlib import Path


class TicketStore:
    def __init__(self, store_file):
        self.store_file = Path(store_file)
        self.lock = threading.Lock()
        self.ticket_count = 0
        self.store_file.parent.mkdir(parents=True, exist_ok=True)

    def create_ticket(self, payload):
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
            with self.store_file.open("a", encoding="utf-8") as file_handle:
                file_handle.write(line + "\n")
            self.ticket_count += 1
            stored_count = self.ticket_count

        return record, stored_count


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

            if message_type == "CREATE_TICKET":
                try:
                    ticket, stored_count = self.server.ticket_store.create_ticket(payload)
                except ValueError as exc:
                    self.send_json(
                        {
                            "type": "CREATE_TICKET_RESPONSE",
                            "status": "error",
                            "code": "invalid_payload",
                            "message": str(exc),
                        }
                    )
                    continue
                except Exception as exc:
                    self.send_json(
                        {
                            "type": "CREATE_TICKET_RESPONSE",
                            "status": "error",
                            "code": "storage_failed",
                            "message": f"No fue posible almacenar el ticket: {exc}",
                        }
                    )
                    continue

                self.send_json(
                    {
                        "type": "CREATE_TICKET_RESPONSE",
                        "status": "ok",
                        "ticket_id": ticket["ticket_id"],
                        "ticket": ticket,
                        "store_file": str(self.server.ticket_store.store_file),
                        "stored_count": stored_count,
                    }
                )
                continue

            self.send_json({"type": "ERROR", "code": "unknown_message_type"})


class TicketingServiceServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, server_address, handler_class, ticket_store):
        super().__init__(server_address, handler_class)
        self.ticket_store = ticket_store


def parse_args():
    parser = argparse.ArgumentParser(description="Ticketing Service para la práctica 6")
    parser.add_argument("--host", default="127.0.0.1", help="Host para escuchar conexiones")
    parser.add_argument("--port", type=int, default=7000, help="Puerto para escuchar conexiones")
    parser.add_argument("--store-file", default="tickets/tickets.txt", help="Archivo de almacenamiento de tickets")
    return parser.parse_args()


def main():
    args = parse_args()
    ticket_store = TicketStore(args.store_file)
    server = TicketingServiceServer((args.host, args.port), TicketingServiceHandler, ticket_store)

    print("Ticketing Service iniciado")
    print(f"Escuchando en {args.host}:{args.port}")
    print(f"Archivo de tickets: {ticket_store.store_file}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Ticketing Service] Interrupción recibida. Cerrando servicio...")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
