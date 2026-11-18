"""Texturas ilustrativas. No determinan transitabilidad ni colisiones."""
from collections import Counter
import numpy as np

TERRENOS = {
    ".": ((104, 155, 62), "Pasto (.)"),
    "T": ((27, 78, 40), "Bosque (T) - bloqueado"),
    "W": ((35, 113, 176), "Agua (W) - bloqueada"),
    "@": ((30, 29, 36), "Exterior (@)"),
    "O": ((30, 29, 36), "Exterior (O)"),
    "S": ((103, 116, 59), "Pantano (S) - bloqueado en el modelo actual"),
    "G": ((104, 155, 62), "Terreno (G) - bloqueado en el modelo actual"),
}


def crear_textura_mapa(mapa):
    """Una tesela de 8x8 pixeles por celda, sin mezclar terrenos vecinos.

    Los patrones son ilustrativos; posiciones y tipos proceden del dataset.
    La imagen es independiente de la matriz usada para buscar caminos.
    """
    if not mapa or not mapa[0] or any(len(f) != len(mapa[0]) for f in mapa):
        raise ValueError("El mapa debe ser rectangular y no vacio.")
    conteos = Counter(celda for fila in mapa for celda in fila)
    desconocidos = set(conteos) - set(TERRENOS)
    if desconocidos:
        raise ValueError(f"Simbolos desconocidos: {sorted(desconocidos)}")
    print("Simbolos del mapa:", dict(conteos))
    if conteos["G"] or conteos["S"]:
        print("Aviso: G/S son transitables segun el formato, pero se conserva "
              "su bloqueo en la matriz actual.")

    simbolos = list(TERRENOS)
    indices = {simbolo: i for i, simbolo in enumerate(simbolos)}
    ids = np.array([[indices[c] for c in fila] for fila in mapa], dtype=np.uint8)
    teselas = np.empty((len(simbolos), 8, 8, 3), dtype=np.uint8)
    y, x = np.indices((8, 8))
    for simbolo, i in indices.items():
        color = np.array(TERRENOS[simbolo][0], dtype=np.int16)
        # Variacion determinista dentro de cada celda, sin ruido aleatorio.
        variacion = ((x * 3 + y * 5) % 7 - 3) * 2
        tesela = np.clip(color + variacion[..., None], 0, 255).astype(np.uint8)
        if simbolo in (".", "G"):
            tesela[2:5, 2] = (135, 180, 76)
            tesela[5:7, 6] = (77, 128, 48)
        elif simbolo == "T":
            tesela[5:8, 3:5] = (89, 64, 36)  # tronco
            copa = (y >= 1) & (y <= 5) & (abs(x - 3.5) <= y / 2)
            tesela[copa] = (43, 112, 54)
            tesela[3:5, 3] = (70, 135, 64)
        elif simbolo == "W":
            tesela[(y == 2) & (x >= 1) & (x <= 4)] = (77, 159, 203)
            tesela[(y == 6) & (x >= 3)] = (56, 143, 194)
        elif simbolo == "S":
            tesela[4:6, 1:6] = (69, 104, 94)
        teselas[i] = tesela

    filas, columnas = ids.shape
    imagen = teselas[ids].transpose(0, 2, 1, 3, 4).reshape(
        filas * 8, columnas * 8, 3
    )
    return imagen

