# Practica 01 - Daniela Maldonado
import queue
import random
import threading
import time
import tkinter as tk

FILAS = 25
COLUMNAS = 40
TOTAL_ASIENTOS = FILAS * COLUMNAS
COMPRADORES_POR_ASIENTO = 2
TOTAL_COMPRADORES = TOTAL_ASIENTOS * COMPRADORES_POR_ASIENTO


estado_asientos = [[False for _ in range(COLUMNAS)] for _ in range(FILAS)]
locks_asientos = [[threading.Lock() for _ in range(COLUMNAS)] for _ in range(FILAS)]

asientos_vendidos = 0
lock_asientos_vendidos = threading.Lock()
lock_terminal = threading.Lock()

venta_finalizada = threading.Event()
ui_updates = queue.Queue()
threads = []
cierre_iniciado = False
hitos_reportados = set()
ventas_inicio_ts = None
ventas_fin_ts = None

estadisticas_tiempo = {
	"compradores_exitosos": 0,
	"compradores_sin_compra": 0,
	"tiempo_total_exitosos": 0.0,
	"tiempo_busqueda_exitosos": 0.0,
	"tiempo_compra_exitosos": 0.0,
	"tiempo_espera_azar_exitosos": 0.0,
	"tiempo_total_sin_compra": 0.0,
	"tiempo_espera_azar_sin_compra": 0.0,
	"intentos_exitosos": 0,
	"intentos_sin_compra": 0,
	"intentos_totales": 0,
}
lock_estadisticas_tiempo = threading.Lock()


def avg(total, count):
	if count == 0:
		return 0.0
	return total / count


def attempt_purchase(buyer_id):
	# Aquí es la venta.
	global asientos_vendidos
	start_buyer = time.perf_counter()
	tiempo_espera_azar_local = 0.0
	intentos_local = 0
	comprado = False
	tiempo_compra = 0.0

	while not venta_finalizada.is_set():
		tiempo_espera = random.uniform(0.1, 2.0)
		time.sleep(tiempo_espera)
		tiempo_espera_azar_local += tiempo_espera
		intentos_local += 1

		row = random.randint(0, FILAS - 1)
		col = random.randint(0, COLUMNAS - 1)

		lock = locks_asientos[row][col]
		acquired = lock.acquire(timeout=0.01)
		if not acquired:
			continue

		try:
			if estado_asientos[row][col]:
				continue

			compra_inicio = time.perf_counter()
			with lock_asientos_vendidos:
				if asientos_vendidos >= TOTAL_ASIENTOS:
					venta_finalizada.set()
					break

				estado_asientos[row][col] = True
				asientos_vendidos += 1
				sold_now = asientos_vendidos
			tiempo_compra = time.perf_counter() - compra_inicio

			ui_updates.put((row, col, buyer_id, sold_now))

			if sold_now >= TOTAL_ASIENTOS:
				venta_finalizada.set()

			comprado = True
			break
		finally:
			lock.release()

	tiempo_total_buyer = time.perf_counter() - start_buyer
	tiempo_busqueda_buyer = max(0.0, tiempo_total_buyer - tiempo_compra)

	with lock_estadisticas_tiempo:
		estadisticas_tiempo["intentos_totales"] += intentos_local
		if comprado:
			estadisticas_tiempo["compradores_exitosos"] += 1
			estadisticas_tiempo["tiempo_total_exitosos"] += tiempo_total_buyer
			estadisticas_tiempo["tiempo_busqueda_exitosos"] += tiempo_busqueda_buyer
			estadisticas_tiempo["tiempo_compra_exitosos"] += tiempo_compra
			estadisticas_tiempo["tiempo_espera_azar_exitosos"] += tiempo_espera_azar_local
			estadisticas_tiempo["intentos_exitosos"] += intentos_local
		else:
			estadisticas_tiempo["compradores_sin_compra"] += 1
			estadisticas_tiempo["tiempo_total_sin_compra"] += tiempo_total_buyer
			estadisticas_tiempo["tiempo_espera_azar_sin_compra"] += tiempo_espera_azar_local
			estadisticas_tiempo["intentos_sin_compra"] += intentos_local


def print_timing_summary():
	# Aquí se imprime el resumen de tiempos.
	con_exito = estadisticas_tiempo["compradores_exitosos"]
	sin_compra = estadisticas_tiempo["compradores_sin_compra"]

	print("Resumen de tiempos:")
	print(f"- Tiempo total general de la simulación: {ventas_fin_ts - ventas_inicio_ts:.4f} s")
	print(
		f"- Promedio por comprador exitoso (buscar + comprar): "
		f"{avg(estadisticas_tiempo['tiempo_total_exitosos'], con_exito):.4f} s"
	)
	print(
		f"- Promedio de búsqueda por comprador exitoso: "
		f"{avg(estadisticas_tiempo['tiempo_busqueda_exitosos'], con_exito):.4f} s"
	)
	print(
		f"- Promedio de compra por comprador exitoso: "
		f"{avg(estadisticas_tiempo['tiempo_compra_exitosos'], con_exito):.6f} s"
	)
	print(
		f"- Promedio de espera aleatoria por comprador exitoso: "
		f"{avg(estadisticas_tiempo['tiempo_espera_azar_exitosos'], con_exito):.4f} s"
	)
	print(
		f"- Promedio de intentos por comprador exitoso: "
		f"{avg(estadisticas_tiempo['intentos_exitosos'], con_exito):.2f}"
	)
	print(
		f"- Promedio por comprador sin compra: "
		f"{avg(estadisticas_tiempo['tiempo_total_sin_compra'], sin_compra):.4f} s"
	)
	print(
		f"- Promedio de espera aleatoria por comprador sin compra: "
		f"{avg(estadisticas_tiempo['tiempo_espera_azar_sin_compra'], sin_compra):.4f} s"
	)
	print(
		f"- Promedio de intentos por comprador sin compra: "
		f"{avg(estadisticas_tiempo['intentos_sin_compra'], sin_compra):.2f}"
	)


def process_ui_updates():
	# Aquí se actualiza la vista.
	while True:
		try:
			row, col, _buyer_id, _sold_now = ui_updates.get_nowait()
		except queue.Empty:
			break

		seat_id = seat_items[row][col]
		canvas.itemconfig(seat_id, fill="blue")
		remaining = TOTAL_ASIENTOS - _sold_now
		compradores_que_compraron = _sold_now
		compradores_buscando = TOTAL_COMPRADORES - compradores_que_compraron

		buyers_total_label.config(text=f"Compradores creados: {TOTAL_COMPRADORES}")
		buyers_bought_label.config(text=f"Compradores que ya compraron: {compradores_que_compraron}")
		buyers_searching_label.config(text=f"Compradores que siguen buscando: {compradores_buscando}")
		free_label.config(text=f"Asientos libres: {remaining}")

		with lock_terminal:
			for porcentaje, umbral in (
				(25, int(TOTAL_ASIENTOS * 0.25)),
				(50, int(TOTAL_ASIENTOS * 0.50)),
				(75, int(TOTAL_ASIENTOS * 0.75)),
				(100, TOTAL_ASIENTOS),
			):
				if _sold_now >= umbral and porcentaje not in hitos_reportados:
					hitos_reportados.add(porcentaje)
					print(f"Actualización: {porcentaje}% de boletos vendidos ({_sold_now}/{TOTAL_ASIENTOS}).")

	if venta_finalizada.is_set() and ui_updates.empty():
		root.after(150, finalize_and_close)
		return

	root.after(30, process_ui_updates)


def finalize_and_close():
	# Aquí termina la venta.
	global cierre_iniciado, ventas_fin_ts
	if cierre_iniciado:
		return
	cierre_iniciado = True

	for thread in threads:
		thread.join()

	ventas_fin_ts = time.perf_counter()

	with lock_terminal:
		if 100 not in hitos_reportados:
			hitos_reportados.add(100)
			print(f"Actualización: 100% de boletos vendidos ({asientos_vendidos}/{TOTAL_ASIENTOS}).")
		print("Actualización: la venta ha concluido.")
		print_timing_summary()

	popup = tk.Toplevel(root)
	popup.title("Fin de venta")
	popup.transient(root)
	popup.resizable(False, False)

	message_label = tk.Label(popup, text="La venta ha concluido", font=("Arial", 12), padx=24, pady=20)
	message_label.pack()

	root.update_idletasks()
	popup.update_idletasks()
	x = root.winfo_rootx() + (root.winfo_width() - popup.winfo_width()) // 2
	y = root.winfo_rooty() + (root.winfo_height() - popup.winfo_height()) // 2
	popup.geometry(f"+{x}+{y}")

	def close_all():
		# Aquí se cierra todo.
		if popup.winfo_exists():
			popup.destroy()
		root.destroy()

	root.after(3000, close_all)


def start_sales():
	# Aquí se crean los compradores.
	global ventas_inicio_ts
	ventas_inicio_ts = time.perf_counter()

	with lock_terminal:
		print("Bienvenido a la compra de boletos del Foro Dani")
		print(f"Número de asientos disponibles: {TOTAL_ASIENTOS}")
		print(f"Número de compradores registrados: {TOTAL_COMPRADORES}")
		print("Actualizaciones de venta:")

	for buyer in range(1, TOTAL_COMPRADORES + 1):
		thread = threading.Thread(target=attempt_purchase, args=(buyer,), daemon=False)
		threads.append(thread)
		thread.start()
		time.sleep(0.0005)


def show_start_countdown(seconds=3):
	# Aquí inicia la cuenta regresiva.
	popup = tk.Toplevel(root)
	popup.title("Inicio de venta")
	popup.transient(root)
	popup.resizable(False, False)

	message_label = tk.Label(popup, font=("Arial", 12), padx=20, pady=18)
	message_label.pack()

	def center_popup():
		# Aquí se centra el pop up.
		root.update_idletasks()
		popup.update_idletasks()
		x = root.winfo_rootx() + (root.winfo_width() - popup.winfo_width()) // 2
		y = root.winfo_rooty() + (root.winfo_height() - popup.winfo_height()) // 2
		popup.geometry(f"+{x}+{y}")

	def tick(remaining):
		# Aquí va el conteo.
		if remaining > 0:
			suffix = "segundo" if remaining == 1 else "segundos"
			message_label.config(text=f"La venta iniciará en {remaining} {suffix}")
			center_popup()
			root.after(1000, tick, remaining - 1)
			return

		popup.destroy()
		start_sales()

	tick(seconds)


root = tk.Tk()
root.title("Simulación de compra de boletos")

label_margin = 30
cell_size = 18
grid_width = COLUMNAS * cell_size
grid_height = FILAS * cell_size
canvas_width = label_margin + grid_width + 10
canvas_height = label_margin + grid_height + 10

main_frame = tk.Frame(root)
main_frame.pack(padx=10, pady=10)

canvas = tk.Canvas(main_frame, width=canvas_width, height=canvas_height, bg="white")
canvas.pack(side="left")

info_frame = tk.Frame(main_frame, padx=16)
info_frame.pack(side="left", fill="y")

radius = int(cell_size * 0.35)
seat_items = [[None for _ in range(COLUMNAS)] for _ in range(FILAS)]

for c in range(COLUMNAS):
	label_x = label_margin + c * cell_size + cell_size // 2
	canvas.create_text(label_x, 12, text=str(c + 1), fill="black", font=("Arial", 8))

for r in range(FILAS):
	label_y = label_margin + r * cell_size + cell_size // 2
	canvas.create_text(12, label_y, text=str(r + 1), fill="black", font=("Arial", 8))

for r in range(FILAS):
	for c in range(COLUMNAS):
		center_x = label_margin + c * cell_size + cell_size // 2
		center_y = label_margin + r * cell_size + cell_size // 2
		seat = canvas.create_oval(
			center_x - radius,
			center_y - radius,
			center_x + radius,
			center_y + radius,
			fill="gray",
			outline="black",
		)
		seat_items[r][c] = seat

buyers_total_label = tk.Label(info_frame, text=f"Compradores creados: {TOTAL_COMPRADORES}", font=("Arial", 11), anchor="w")
buyers_total_label.pack(fill="x", pady=(4, 8))

buyers_bought_label = tk.Label(info_frame, text="Compradores que ya compraron: 0", font=("Arial", 11), anchor="w")
buyers_bought_label.pack(fill="x", pady=4)

buyers_searching_label = tk.Label(info_frame, text=f"Compradores que siguen buscando: {TOTAL_COMPRADORES}", font=("Arial", 11), anchor="w")
buyers_searching_label.pack(fill="x", pady=4)

free_label = tk.Label(info_frame, text=f"Asientos libres: {TOTAL_ASIENTOS}", font=("Arial", 11), anchor="w")
free_label.pack(fill="x", pady=4)

root.after(30, process_ui_updates)
root.after(100, show_start_countdown, 3)
root.mainloop()
