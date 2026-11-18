from pathlib import Path
from logica_pathfinding import (astar_busqueda, bfs_busqueda, contar_aristas, convertir_a_matriz, crear_grafo, heuristica_manhattan, leer_mapa)
from terrenos import TERRENOS, crear_textura_mapa
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch
import numpy as np




# Colores y etiquetas solo visuales: NO definen la transitabilidad.




def dibujar_terreno(ax, matriz, textura=None):
    if textura is None:
        ax.imshow(matriz, cmap=ListedColormap(["black", "lightgray"]),
                  interpolation="nearest", origin="upper", zorder=0)
    else:
        filas, columnas = len(matriz), len(matriz[0])
        ax.imshow(textura, interpolation="nearest", origin="upper",
                  extent=(-0.5, columnas - 0.5, filas - 0.5, -0.5), zorder=0)


def visualizar_mapa(matriz, textura=None, mapa_original=None):
    print("Generando visualizacion del mapa completo...")
    fig, ax = plt.subplots(figsize=(10, 10))
    dibujar_terreno(ax, matriz, textura)
    ax.set_title("Mapa Dark Forest - Warcraft III")
    ax.set_xlabel("Columnas")
    ax.set_ylabel("Filas")
    if mapa_original is not None:
        presentes = {c for fila in mapa_original for c in fila}
        leyenda = [Patch(facecolor=np.array(color) / 255, label=etiqueta)
                   for simbolo, (color, etiqueta) in TERRENOS.items()
                   if simbolo in presentes]
        ax.legend(handles=leyenda, loc="upper center", bbox_to_anchor=(0.5, -0.08),
                  ncol=2, fontsize=8)
    fig.savefig("darkforest_visualizacion.png", dpi=300, bbox_inches="tight")
    print("Imagen guardada: darkforest_visualizacion.png")
    plt.show()






def visualizar_subgrafo(grafo, fila_inicio, columna_inicio, tamano,
                        *, guardar=False, dpi=150, textura=None):
    """Dibuja una region sin modificar el grafo utilizado por la busqueda.

    guardar=True exporta darkforest_subgrafo.png; dpi=300 sirve para el informe.
    """
    if tamano <= 0:
        raise ValueError("El tamano debe ser mayor que cero.")

    fila_final = fila_inicio + tamano
    columna_final = columna_inicio + tamano

    # Para ventanas pequenas consultamos solo sus coordenadas. Para ventanas
    # grandes recorremos los nodos existentes una sola vez.
    if tamano * tamano < len(grafo):
        nodos = [
            (fila, columna)
            for fila in range(fila_inicio, fila_final)
            for columna in range(columna_inicio, columna_final)
            if (fila, columna) in grafo
        ]
    else:
        nodos = [
            nodo for nodo in grafo
            if fila_inicio <= nodo[0] < fila_final
            and columna_inicio <= nodo[1] < columna_final
        ]

    visibles = set(nodos)
    segmentos = []
    for nodo in nodos:
        for vecino in grafo[nodo]:
            # El grafo es no dirigido: dibujar A-B una vez, sin borrar B-A.
            if vecino in visibles and nodo < vecino:
                segmentos.append(((nodo[1], nodo[0]),
                                  (vecino[1], vecino[0])))

    fig, ax = plt.subplots(figsize=(10, 10))
    if textura is not None:
        # Una sola imagen de fondo, alineada con las coordenadas del grafo.
        filas_mapa, columnas_mapa = textura.shape[0] // 8, textura.shape[1] // 8
        ax.imshow(textura, interpolation="nearest", origin="upper",
                  extent=(-0.5, columnas_mapa - 0.5, filas_mapa - 0.5, -0.5),
                  zorder=0)
    escala = min(1.0, 50.0 / tamano)
    ax.add_collection(LineCollection(
        segmentos, colors="red", linewidths=max(0.15, escala), zorder=1
    ))
    if nodos:
        filas, columnas = zip(*nodos)
        ax.scatter(columnas, filas, color="blue", s=25 * escala ** 2,
                   linewidths=0, zorder=2)

    ax.set_title(
        f"Subgrafo Dark Forest: {len(nodos)} nodos, {len(segmentos)} aristas"
    )
    ax.set_xlabel("Columnas")
    ax.set_ylabel("Filas")
    ax.set_xlim(columna_inicio - 0.5, columna_final - 0.5)
    ax.set_ylim(fila_final - 0.5, fila_inicio - 0.5)
    ax.set_aspect("equal")
    if tamano <= 50:
        ax.grid(alpha=0.2)
        ax.set_axisbelow(True)

    # La exploracion no necesita exportar una imagen en cada ejecucion.
    if guardar:
        fig.savefig("darkforest_subgrafo.png", dpi=dpi, bbox_inches="tight")
        print("Imagen guardada: darkforest_subgrafo.png")

    plt.show()
    return fig, ax








def visualizar_ruta(matriz, ruta, inicio, objetivo,
                    algoritmo="BFS", archivo="ruta_bfs.png", textura=None):


    if ruta is None:
        print("No existe una ruta para visualizar.")
        return

    fig, ax = plt.subplots(figsize=(10, 10))
    dibujar_terreno(ax, matriz, textura)

    filas_ruta = []
    columnas_ruta = []

    for nodo in ruta:

        fila, columna = nodo

        filas_ruta.append(fila)
        columnas_ruta.append(columna)

    ax.plot(
        columnas_ruta,
        filas_ruta,
        color="yellow",
        linewidth=2,
        label=f"Ruta {algoritmo}"
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

    ax.set_title(f"Ruta encontrada mediante {algoritmo}")
    ax.set_xlabel("Columnas")
    ax.set_ylabel("Filas")

    ax.legend()

    plt.savefig(
        archivo,
        dpi=300,
        bbox_inches="tight"
    )

    print(f"Imagen guardada: {archivo}")

    plt.show()
# -------------------------
# Programa principal
# -------------------------


def main():
    # 1. Leer archivo original
    mapa_original = leer_mapa(
        Path(__file__).resolve().parent / "DataSet" / "darkforest.map"
    )

    print("Filas:", len(mapa_original))
    print("Columnas:", len(mapa_original[0]))


    # 2. Convertir el mapa a matriz de navegación
    matriz = convertir_a_matriz(
        mapa_original
    )


    # 3. Texturas del mapa original, independientes de la navegacion.
    textura_mapa = crear_textura_mapa(mapa_original)
    visualizar_mapa(matriz, textura_mapa, mapa_original)


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
        tamano=20,
        guardar=True,
        dpi=300,
        textura=textura_mapa
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
                objetivo,
                textura=textura_mapa
            )

        else:

            print(
                "No existe una ruta entre los puntos."
            )

        # 10. Ejecutar A* con los mismos parametros que BFS.
        ruta_astar, visitados_astar = astar_busqueda(
            grafo,
            inicio,
            objetivo
        )

        if ruta_astar is not None:
            print("Ruta encontrada mediante A*.")
            print("Cantidad de movimientos:", len(ruta_astar) - 1)
            print("Nodos descubiertos por A*:", len(visitados_astar))

            # 11. Guardar por separado para conservar tambien la ruta BFS.
            visualizar_ruta(
                matriz,
                ruta_astar,
                inicio,
                objetivo,
                algoritmo="A*",
                archivo="ruta_astar.png",
                textura=textura_mapa
            )
        else:
            print("A*: No existe una ruta entre los puntos.")


if __name__ == "__main__":
    main()
