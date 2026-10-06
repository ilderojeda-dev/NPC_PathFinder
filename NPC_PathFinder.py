import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from collections import deque

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

def visualizar_mapa(matriz):

    print("Generando visualización del mapa completo...")

    colores = ListedColormap(["black", "lightgray"])

    plt.figure(figsize=(10, 10))

    plt.imshow(
        matriz,
        cmap=colores,
        interpolation="nearest",
        origin="upper"
    )

    plt.title("Mapa Dark Forest - Warcraft III")
    plt.xlabel("Columnas")
    plt.ylabel("Filas")

    plt.savefig(
        "darkforest_visualizacion.png",
        dpi=300,
        bbox_inches="tight"
    )

    print("Imagen guardada: darkforest_visualizacion.png")

    plt.show()

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


def visualizar_subgrafo(grafo, fila_inicio, columna_inicio, tamano):
    fig, ax = plt.subplots(figsize=(10, 10))

    fila_final = fila_inicio + tamano
    columna_final = columna_inicio + tamano

    # Dibujar aristas
    for nodo in grafo:
        fila, columna = nodo

        if (
            fila_inicio <= fila < fila_final and
            columna_inicio <= columna < columna_final
        ):
            for vecino in grafo[nodo]:
                fila_vecino, columna_vecino = vecino

                if (
                    fila_inicio <= fila_vecino < fila_final and
                    columna_inicio <= columna_vecino < columna_final
                ):
                    ax.plot(
                        [columna, columna_vecino],
                        [fila, fila_vecino],
                        color="red",
                        linewidth=1
                    )

    # Dibujar nodos
    for nodo in grafo:
        fila, columna = nodo

        if (
            fila_inicio <= fila < fila_final and
            columna_inicio <= columna < columna_final
        ):
            ax.scatter(
                columna,
                fila,
                color="blue",
                s=25
            )

    ax.set_title("Subgrafo del mapa Dark Forest")
    ax.set_xlabel("Columnas")
    ax.set_ylabel("Filas")

    # Eje X: izquierda -> derecha
    ax.set_xlim(columna_inicio - 0.5, columna_final - 0.5)

    # Eje Y: arriba -> abajo
    ax.set_ylim(fila_final - 0.5, fila_inicio - 0.5)

    ax.set_aspect("equal")
    ax.grid()

    plt.savefig(
        "darkforest_subgrafo.png",
        dpi=300,
        bbox_inches="tight"
    )

    print("Imagen guardada: darkforest_subgrafo.png")

    plt.show()




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
def visualizar_ruta(matriz, ruta, inicio, objetivo):

    if ruta is None:
        print("No existe una ruta para visualizar.")
        return

    colores = ListedColormap(["black", "lightgray"])

    fig, ax = plt.subplots(figsize=(10, 10))

    ax.imshow(
        matriz,
        cmap=colores,
        interpolation="nearest",
        origin="upper"
    )

    filas_ruta = []
    columnas_ruta = []

    for nodo in ruta:

        fila, columna = nodo

        filas_ruta.append(fila)
        columnas_ruta.append(columna)

    ax.plot(
        columnas_ruta,
        filas_ruta,
        color="blue",
        linewidth=2,
        label="Ruta BFS"
    )

    ax.scatter(
        inicio[1],
        inicio[0],
        color="green",
        s=80,
        label="Inicio"
    )

    ax.scatter(
        objetivo[1],
        objetivo[0],
        color="red",
        s=80,
        label="Objetivo"
    )

    ax.set_title("Ruta encontrada mediante BFS")
    ax.set_xlabel("Columnas")
    ax.set_ylabel("Filas")

    ax.legend()

    plt.savefig(
        "ruta_bfs.png",
        dpi=300,
        bbox_inches="tight"
    )

    print("Imagen guardada: ruta_bfs.png")

    plt.show()
# -------------------------
# Programa principal
# -------------------------


# 1. Leer archivo original
mapa_original = leer_mapa(
    "dataset/darkforest.map"
)

print("Filas:", len(mapa_original))
print("Columnas:", len(mapa_original[0]))


# 2. Convertir el mapa a matriz de navegación
matriz = convertir_a_matriz(
    mapa_original
)


# 3. Visualizar matriz
visualizar_mapa(
    matriz
)


# 4. Convertir matriz a grafo
grafo = crear_grafo(
    matriz
)

print(
    "Cantidad de nodos del grafo:",
    len(grafo)
)

print(
    "Cantidad de aristas:",
    contar_aristas(grafo)
)


# 5. Visualizar subgrafo
visualizar_subgrafo(
    grafo,
    fila_inicio=55,
    columna_inicio=90,
    tamano=20
)


# 6. Definir búsqueda
inicio = (100, 200)
objetivo = (420, 300)


# 7. Verificar posiciones
if inicio not in grafo:

    print(
        "El punto inicial no es transitable."
    )

elif objetivo not in grafo:

    print(
        "El objetivo no es transitable."
    )

else:

    # 8. Ejecutar BFS
    ruta, visitados = bfs_busqueda(
        grafo,
        inicio,
        objetivo
    )

    if ruta is not None:

        print("Ruta encontrada.")

        print(
            "Cantidad de movimientos:",
            len(ruta) - 1
        )

        print(
            "Nodos explorados:",
            len(visitados)
        )

        # 9. Visualizar resultado
        visualizar_ruta(
            matriz,
            ruta,
            inicio,
            objetivo
        )

    else:

        print(
            "No existe una ruta entre los puntos."
        )