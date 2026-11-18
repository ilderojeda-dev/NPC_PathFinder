"""Datos, grafo y busquedas. Sin dependencias graficas."""
from collections import deque
from heapq import heappush, heappop

def leer_mapa(ruta):
    with open(ruta, "r") as archivo:
        lineas = archivo.readlines()

    inicio_mapa = lineas.index("map\n") + 1

    mapa = []

    for linea in lineas[inicio_mapa:]:
        mapa.append(list(linea.strip()))

    return mapa


def convertir_a_matriz(mapa):
    matriz = []

    for fila in mapa:
        nueva_fila = []

        for celda in fila:

            if celda == ".":
                nueva_fila.append(1)   # transitable
            else:
                nueva_fila.append(0)   # obstáculo

        matriz.append(nueva_fila)

    return matriz


def crear_grafo(matriz):
    grafo = {}

    filas = len(matriz)
    columnas = len(matriz[0])

    movimientos = [
        (-1, 0),   # arriba
        (1, 0),    # abajo
        (0, -1),   # izquierda
        (0, 1)     # derecha
    ]

    for fila in range(filas):

        for columna in range(columnas):

            # 1 significa que la posición es transitable
            if matriz[fila][columna] == 1:

                nodo = (fila, columna)
                grafo[nodo] = []

                for movimiento_fila, movimiento_columna in movimientos:

                    nueva_fila = fila + movimiento_fila
                    nueva_columna = columna + movimiento_columna

                    if (
                        0 <= nueva_fila < filas
                        and 0 <= nueva_columna < columnas
                    ):

                        if matriz[nueva_fila][nueva_columna] == 1:

                            vecino = (
                                nueva_fila,
                                nueva_columna
                            )

                            grafo[nodo].append(vecino)

    return grafo


def contar_aristas(grafo):
    cantidad = 0

    for nodo in grafo:
        cantidad += len(grafo[nodo])

    # Cada arista aparece dos veces:
    # A -> B y B -> A
    return cantidad // 2


def bfs_busqueda(grafo, inicio, objetivo):

    cola = deque([inicio])

    visitados = set()
    visitados.add(inicio)

    # Guarda de qué nodo venimos
    anterior = {
        inicio: None
    }

    while cola:

        nodo_actual = cola.popleft()

        # Si encontramos el objetivo
        if nodo_actual == objetivo:
            break

        # Revisar vecinos
        for vecino in grafo[nodo_actual]:

            if vecino not in visitados:

                visitados.add(vecino)
                anterior[vecino] = nodo_actual
                cola.append(vecino)

    # Si nunca encontramos el objetivo
    if objetivo not in anterior:
        return None, visitados

    # Reconstruir la ruta
    ruta = []

    nodo = objetivo

    while nodo is not None:
        ruta.append(nodo)
        nodo = anterior[nodo]

    ruta.reverse()

    return ruta, visitados


def heuristica_manhattan(nodo, objetivo):
    # Distancia minima sin obstaculos para movimientos ortogonales de coste 1.
    return abs(nodo[0] - objetivo[0]) + abs(nodo[1] - objetivo[1])


def astar_busqueda(grafo, inicio, objetivo):
    """A* para el grafo ortogonal de coste unitario creado por crear_grafo.

    Devuelve (ruta, visitados). Como en BFS, visitados cuenta los nodos
    descubiertos, incluidos los que permanecen pendientes de procesar.
    """
    if inicio not in grafo or objetivo not in grafo:
        return None, set()

    costos = {inicio: 0}
    anterior = {inicio: None}
    visitados = {inicio}
    # Entradas: (f = g + h, g, nodo). heapq extrae la menor prioridad.
    pendientes = [(heuristica_manhattan(inicio, objetivo), 0, inicio)]

    while pendientes:
        _, costo_actual, nodo_actual = heappop(pendientes)

        # Una mejora puede dejar una entrada antigua en la cola.
        if costo_actual != costos[nodo_actual]:
            continue

        # Terminar al extraer el objetivo, no al descubrirlo.
        if nodo_actual == objetivo:
            ruta = []
            nodo = objetivo
            while nodo is not None:
                ruta.append(nodo)
                nodo = anterior[nodo]
            ruta.reverse()
            return ruta, visitados

        for vecino in grafo[nodo_actual]:
            nuevo_costo = costo_actual + 1
            if nuevo_costo < costos.get(vecino, float("inf")):
                costos[vecino] = nuevo_costo
                anterior[vecino] = nodo_actual
                visitados.add(vecino)
                prioridad = nuevo_costo + heuristica_manhattan(vecino, objetivo)
                heappush(pendientes, (prioridad, nuevo_costo, vecino))

    return None, visitados

