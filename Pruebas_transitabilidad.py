import pygame
import numpy as np
from pathlib import Path
from collections import deque
from heapq import heappush, heappop
from time import perf_counter
import math
import csv

from obstaculos_dinamicos import (
    GestorObstaculosDinamicos, TAMANOS, MODOS, MODO_RUTA
)


# ============================================================
# 1. CONFIGURACION GENERAL
# ============================================================

CARPETA = Path(__file__).resolve().parent
CARPETA_DATOS = CARPETA / "Datos_generados"
CARPETA_DATOS.mkdir(exist_ok=True)

RUTA_IMAGEN = CARPETA / "Recursos" / "mapa_bosque.png"
RUTA_SPRITE = CARPETA / "Recursos" / "npc_aventurero.png"
RUTA_MASCARA = CARPETA / "Recursos" / "mascara_obstaculos.png"

ANCHO = 1200
ALTO = 900
PANEL = 290   # Mas alto para alojar los controles de obstaculos dinamicos

# Tamaño al que se mostrará cada cuadro del aventurero.
ANCHO_NPC = 32
ALTO_NPC = 48

# Velocidad de desplazamiento del NPC en píxeles del mapa por segundo.
VELOCIDAD_NPC = 150

# Tiempo entre cuadros de la animación al caminar.
INTERVALO_ANIMACION = 0.12

# Tiempo entre cuadros de la animación cuando el NPC está quieto.
INTERVALO_IDLE = 0.30

# Tamaño del rectángulo de referencia en los pies (en píxeles del mapa).
# Hitbox utilizada para colisiones en coordenadas del mapa.
ANCHO_HITBOX_PIES = 15
ALTO_HITBOX_PIES = 7

ALPHA_UMBRAL = 10

# Expansiones de nodos por cuadro durante una busqueda (antes 400). Cada
# expansion cuesta ~3 microsegundos: 2500 por cuadro mantiene ~60 FPS y evita
# pausas largas al replanificar.
LOTE_EXPANSIONES = 2500

# Acercamiento minimo al iniciar el recorrido automatico.
ZOOM_SEGUIMIENTO = 2.0

# ============================================================
# 2. INICIAR PYGAME Y CARGAR EL MAPA
# ============================================================

pygame.init()

pantalla = pygame.display.set_mode((ANCHO, ALTO))
pygame.display.set_caption("Prueba de mapa y animacion del aventurero")

fuente = pygame.font.SysFont("Arial", 14)

if not RUTA_IMAGEN.exists():
    raise FileNotFoundError(
        f"No se encontro la imagen del mapa: {RUTA_IMAGEN.name}"
    )

imagen_original = pygame.image.load(
    str(RUTA_IMAGEN)
).convert()

ancho_mapa = imagen_original.get_width()
alto_mapa = imagen_original.get_height()

print("MAPA CARGADO")
print("Ancho:", ancho_mapa)
print("Alto:", alto_mapa)


# ============================================================
# 3. CONVERTIR LA IMAGEN DEL MAPA EN UNA MATRIZ DE COLORES
# ============================================================

def convertir_a_matriz(imagen):
    """
    Convierte cada color RGB de la imagen en un identificador numerico.

    Cada posicion de la matriz representa un pixel de la imagen.
    Los colores iguales reciben el mismo identificador.
    """

    pixeles = pygame.surfarray.array3d(imagen)

    # Pygame entrega los datos como (columnas, filas, canales).
    # Los cambiamos a (filas, columnas, canales).
    pixeles = np.transpose(pixeles, (1, 0, 2))

    alto = pixeles.shape[0]
    ancho = pixeles.shape[1]

    pixeles_lista = pixeles.reshape(-1, 3)

    colores_unicos, indices = np.unique(
        pixeles_lista,
        axis=0,
        return_inverse=True
    )

    cantidad_colores = len(colores_unicos)

    if cantidad_colores <= 256:
        tipo = np.uint8
    elif cantidad_colores <= 65536:
        tipo = np.uint16
    else:
        tipo = np.uint32

    matriz = indices.reshape(
        alto,
        ancho
    ).astype(tipo)

    return matriz, colores_unicos


matriz, paleta = convertir_a_matriz(imagen_original)

print("\nMATRIZ GENERADA")
print("Filas:", matriz.shape[0])
print("Columnas:", matriz.shape[1])
print("Colores diferentes:", len(paleta))


# ============================================================
# 4. RECONSTRUIR LA IMAGEN A PARTIR DE LA MATRIZ
# ============================================================

def matriz_a_imagen(matriz, paleta):
    """
    Recupera el color RGB de cada identificador de la matriz.
    """

    imagen_rgb = paleta[matriz]

    # Pygame necesita el orden (columnas, filas, canales).
    imagen_rgb = np.transpose(
        imagen_rgb,
        (1, 0, 2)
    )

    superficie = pygame.surfarray.make_surface(imagen_rgb)

    return superficie


imagen_matriz = matriz_a_imagen(matriz, paleta)

pixeles_originales = pygame.surfarray.array3d(imagen_original)
pixeles_reconstruidos = pygame.surfarray.array3d(imagen_matriz)

print(
    "\n¿La reconstruccion conserva los colores?",
    np.array_equal(
        pixeles_originales,
        pixeles_reconstruidos
    )
)


# ============================================================
# 5. CREAR LA MATRIZ BINARIA DE TRANSITABILIDAD
# ============================================================

if not RUTA_MASCARA.exists():
    # El nombre del archivo puede variar (guiones bajos/espacios/acentos).
    _candidatas = sorted(CARPETA.glob("Mapa_obst*.png"))
    if _candidatas:
        RUTA_MASCARA = _candidatas[0]

if not RUTA_MASCARA.exists():
    raise FileNotFoundError(
        "No se encontro la mascara de transitabilidad: "
        f"{RUTA_MASCARA.name}. Coloca este PNG junto al archivo Python."
    )

# Cargamos la máscara conservando su canal alfa.
mascara_original = pygame.image.load(
    str(RUTA_MASCARA)
).convert_alpha()

# Comprobamos que el archivo realmente tenga canal alfa.
# Si no existe, no podemos distinguir transparencia de color negro.
if mascara_original.get_masks()[3] == 0:
    raise ValueError(
        "La mascara no contiene un canal alfa real. "
        "Se necesita un PNG con transparencia."
    )

ancho_mascara = mascara_original.get_width()
alto_mascara = mascara_original.get_height()

# La máscara debe coincidir exactamente con el mapa base.
# No la redimensionamos automáticamente porque eso podría desalinear
# las zonas transitables con el escenario.
if ancho_mascara != ancho_mapa or alto_mascara != alto_mapa:
    raise ValueError(
        "La mascara y el mapa tienen dimensiones diferentes. "
        f"Mapa: {ancho_mapa}x{alto_mapa}; "
        f"mascara: {ancho_mascara}x{alto_mascara}. "
        "Corrige la máscara para que tenga el mismo tamaño y alineación."
    )

# Pygame devuelve el canal alfa con forma (columnas, filas).
# Lo transponemos para obtener una matriz [fila][columna] = [y][x].
alfa_pixeles = pygame.surfarray.array_alpha(mascara_original)
alfa_pixeles = np.transpose(alfa_pixeles, (1, 0))

# Alfa <= 10: transitable. Alfa > 10: obstaculo.
matriz_transitabilidad = np.where(
    alfa_pixeles <= ALPHA_UMBRAL,
    1,
    0
).astype(np.uint8)

def crear_matriz_posiciones_validas():
    """Comprueba los 105 pixeles con sumas acumuladas, en O(alto*ancho)."""
    alto, ancho = matriz_transitabilidad.shape
    validas = np.zeros((alto, ancho), dtype=np.uint8)
    h, w = ALTO_HITBOX_PIES, ANCHO_HITBOX_PIES
    if alto < h or ancho < w:
        return validas
    acumulada = np.pad(matriz_transitabilidad.astype(np.int32), ((1, 0), (1, 0)))
    acumulada = acumulada.cumsum(axis=0).cumsum(axis=1)
    sumas = (acumulada[h:, w:] - acumulada[:-h, w:]
             - acumulada[h:, :-w] + acumulada[:-h, :-w])
    validas[h//2:alto-h//2, w//2:ancho-w//2] = (sumas == h*w)
    return validas


def es_posicion_valida(x, y):
    alto, ancho = matriz_posiciones_validas.shape
    return 0 <= x < ancho and 0 <= y < alto and bool(matriz_posiciones_validas[y, x])


def obtener_vecinos(x, y):
    """Grafo implicito: coordenadas (x,y), matriz [y,x], sin diagonales."""
    if not es_posicion_valida(x, y):
        return []
    return [(nx, ny) for nx, ny in
            ((x,y-1), (x,y+1), (x-1,y), (x+1,y))
            if es_posicion_valida(nx, ny)]


def centro_hitbox():
    # npc_y conserva el borde inferior del sprite. La hitbox ocupa
    # [npc_y-7,npc_y); el centro de sus pixeles esta en npc_y-4.
    return int(npc_x), int(npc_y) - (ALTO_HITBOX_PIES//2 + 1)


def marcar_rastro(x, y):
    """Pinta un pixel del mundo por cada nodo realmente visitado."""
    global rastro_modificado
    if capa_rastro.get_at((x, y)).a == 0:
        capa_rastro.set_at((x, y), (255, 0, 0, 255))
        rastro_modificado = True


def dibujar_rastro():
    """Capa independiente del mapa y las matrices, con el mismo zoom."""
    global rastro_escalado, rastro_modificado
    tamano = mapa_escalado.get_size()
    if (rastro_modificado or rastro_escalado is None
            or rastro_escalado.get_size() != tamano):
        rastro_escalado = pygame.transform.scale(capa_rastro, tamano)
        rastro_modificado = False
    pantalla.blit(rastro_escalado,
                  (int(desplazamiento_x), int(desplazamiento_y)))


def mover_npc_con_colisiones(dx, dy, distancia):
    global npc_x, npc_y, resto_movimiento, sentido_movimiento
    if dx:
        dy = 0  # Prioridad horizontal, sin aristas diagonales.
    sentido = (dx, dy)
    if sentido != sentido_movimiento:
        resto_movimiento = 0.0
        sentido_movimiento = sentido
    if not dx and not dy:
        resto_movimiento = 0.0
        return False
    resto_movimiento += distancia
    pasos = int(resto_movimiento)
    resto_movimiento -= pasos
    x, y = centro_hitbox()
    movido = False
    for _ in range(pasos):
        nx, ny = x+dx, y+dy
        if not es_posicion_valida(nx, ny):
            resto_movimiento = 0.0
            break
        x, y = nx, ny
        marcar_rastro(x, y)
        movido = True
    npc_x = x
    npc_y = y + ALTO_HITBOX_PIES//2 + 1
    return movido


# Precalculo unico; no se almacenan objetos por nodo ni listas de aristas.
# Tres capas: estatica (intocable) + mascara dinamica + efectiva.
_t_prep = perf_counter()
matriz_posiciones_validas_estatica = crear_matriz_posiciones_validas()
TIEMPO_PREPARACION_ESTATICA = perf_counter() - _t_prep
SEMILLA_INICIAL = 2024
gestor_obstaculos = GestorObstaculosDinamicos(
    matriz_transitabilidad, matriz_posiciones_validas_estatica,
    ANCHO_HITBOX_PIES, ALTO_HITBOX_PIES, SEMILLA_INICIAL)
# La efectiva conserva el nombre original: BFS, A*, colisiones, clics y el
# visualizador de subgrafos la consultan sin cambios.
matriz_posiciones_validas = gestor_obstaculos.efectiva
cantidad_validas = int(np.count_nonzero(matriz_posiciones_validas))
cantidad_validas_estatica = cantidad_validas
cantidad_invalidas = int(matriz_posiciones_validas.size) - cantidad_validas
porcentaje_validas = 100 * cantidad_validas / matriz_posiciones_validas.size
print("POSICIONES VALIDAS DEL NPC:", matriz_posiciones_validas.shape)
print("Validas:", cantidad_validas, "Invalidas:", cantidad_invalidas)
print(f"Porcentaje valido: {porcentaje_validas:.2f}%")
colores_posiciones = np.empty((*matriz_posiciones_validas.shape,3), dtype=np.uint8)
colores_posiciones[:] = (220,55,55)
colores_posiciones[matriz_posiciones_validas == 1] = (35,190,85)
imagen_posiciones_validas = pygame.surfarray.make_surface(colores_posiciones.transpose(1,0,2))


cantidad_transitable = int(np.count_nonzero(matriz_transitabilidad == 1))
cantidad_obstaculos = int(np.count_nonzero(matriz_transitabilidad == 0))
total_celdas = int(matriz_transitabilidad.size)

porcentaje_transitable = cantidad_transitable * 100 / total_celdas
porcentaje_obstaculos = cantidad_obstaculos * 100 / total_celdas

# Creamos una imagen de previsualización:
# verde = 1 (transitable), rojo = 0 (obstáculo).
colores_binarios = np.zeros(
    (alto_mapa, ancho_mapa, 3),
    dtype=np.uint8
)
colores_binarios[matriz_transitabilidad == 1] = (35, 190, 85)
colores_binarios[matriz_transitabilidad == 0] = (220, 55, 55)

# Pygame necesita los datos en el orden (columnas, filas, canales).
imagen_binaria_rgb = np.transpose(
    colores_binarios,
    (1, 0, 2)
)
imagen_transitabilidad = pygame.surfarray.make_surface(
    imagen_binaria_rgb
)

# Guardamos la matriz para utilizarla posteriormente con los algoritmos.
np.save(
    CARPETA_DATOS / "matriz_transitabilidad.npy",
    matriz_transitabilidad
)

# También guardamos una versión CSV para poder inspeccionar sus 0 y 1.
np.savetxt(
    CARPETA_DATOS / "matriz_transitabilidad.csv",
    matriz_transitabilidad,
    delimiter=",",
    fmt="%d"
)

# Guardamos la previsualización de colores.
pygame.image.save(
    imagen_transitabilidad,
    str(CARPETA_DATOS / "vista_matriz_transitabilidad.png")
)

print("\nMATRIZ BINARIA DE TRANSITABILIDAD")
print("Filas:", matriz_transitabilidad.shape[0])
print("Columnas:", matriz_transitabilidad.shape[1])
print(
    f"Transitable (1): {cantidad_transitable:,} "
    f"({porcentaje_transitable:.2f}%)"
)
print(
    f"Obstaculos (0): {cantidad_obstaculos:,} "
    f"({porcentaje_obstaculos:.2f}%)"
)
print("Matriz guardada en matriz_transitabilidad.npy")
print("CSV guardado en matriz_transitabilidad.csv")
print("Vista guardada en vista_matriz_transitabilidad.png")


# ============================================================
# 6. GUARDAR LA MATRIZ Y SU PALETA
# ============================================================

np.savez_compressed(
    CARPETA_DATOS / "matriz_colores.npz",
    matriz=matriz,
    paleta=paleta
)

print("Matriz guardada en matriz_colores.npz")


# ============================================================
# 7. CARGAR Y DIVIDIR EL SPRITE DEL AVENTURERO
# ============================================================

if not RUTA_SPRITE.exists():
    raise FileNotFoundError(
        f"No se encontro el sprite: {RUTA_SPRITE.name}"
    )

# convert_alpha conserva la transparencia del archivo PNG.
hoja_sprites = pygame.image.load(
    str(RUTA_SPRITE)
).convert_alpha()

# El spritesheet nuevo mide 128 x 240 píxeles:
# 4 columnas x 5 filas = 20 cuadros.
# Cada cuadro ya mide exactamente 32 x 48 píxeles.
COLUMNAS_SPRITE = 4
FILAS_SPRITE = 5

if hoja_sprites.get_width() % COLUMNAS_SPRITE != 0:
    raise ValueError(
        "El ancho del sprite no se puede dividir exactamente en 4 columnas."
    )

if hoja_sprites.get_height() % FILAS_SPRITE != 0:
    raise ValueError(
        "El alto del sprite no se puede dividir exactamente en 5 filas."
    )

ancho_frame_original = hoja_sprites.get_width() // COLUMNAS_SPRITE
alto_frame_original = hoja_sprites.get_height() // FILAS_SPRITE

if ancho_frame_original != ANCHO_NPC or alto_frame_original != ALTO_NPC:
    raise ValueError(
        f"Cada cuadro deberia medir {ANCHO_NPC}x{ALTO_NPC}, "
        f"pero mide {ancho_frame_original}x{alto_frame_original}."
    )

print("\nSPRITE CARGADO")
print(
    "Tamano de la hoja:",
    hoja_sprites.get_width(),
    "x",
    hoja_sprites.get_height()
)
print(
    "Tamano original de cada cuadro:",
    ancho_frame_original,
    "x",
    alto_frame_original
)
print("Distribucion: 4 columnas x 5 filas = 20 cuadros")

# Distribución confirmada del spritesheet:
# Fila 0: caminar hacia abajo (frente).
# Fila 1: caminar hacia la izquierda.
# Fila 2: caminar hacia la derecha.
# Fila 3: caminar hacia arriba (espalda).
# Fila 4: animación Idle (quieto), mirando hacia el frente.
filas_direccion = {
    "abajo": 0,
    "izquierda": 1,
    "derecha": 2,
    "arriba": 3
}

sprites_npc = {}

for direccion, fila in filas_direccion.items():

    sprites_npc[direccion] = []

    for columna in range(COLUMNAS_SPRITE):

        rectangulo = pygame.Rect(
            columna * ancho_frame_original,
            fila * alto_frame_original,
            ancho_frame_original,
            alto_frame_original
        )

        frame = hoja_sprites.subsurface(rectangulo).copy()

        # No redimensionamos aquí: cada cuadro ya es 32x48.
        sprites_npc[direccion].append(frame)

# La quinta fila contiene los cuatro cuadros de la animación Idle.
sprites_idle = []

for columna in range(COLUMNAS_SPRITE):

    rectangulo = pygame.Rect(
        columna * ancho_frame_original,
        4 * alto_frame_original,
        ancho_frame_original,
        alto_frame_original
    )

    frame = hoja_sprites.subsurface(rectangulo).copy()
    sprites_idle.append(frame)

# ============================================================
# 8. CONFIGURAR LA VISUALIZACION DEL MAPA
# ============================================================

# Modos normales:
# 0 = Imagen original.
# 1 = Imagen reconstruida desde la matriz de colores.
# 2 = Matriz de colores con cuadrícula.
# 3 = Matriz binaria de transitabilidad (G activa/desactiva este modo).

modo = 0
modo_anterior_binario = 0
mostrar_posiciones_validas = False

nombres_vista = [
    "Imagen original",
    "Matriz de colores",
    "Matriz con cuadricula",
    "Matriz binaria de transitabilidad"
]

mostrar_rejilla = False

zoom_minimo = min(
    (ANCHO - 40) / ancho_mapa,
    (ALTO - PANEL - 40) / alto_mapa
)

zoom_maximo = min(
    4.0,
    4500 / max(ancho_mapa, alto_mapa)
)

zoom = zoom_minimo

desplazamiento_x = (
    ANCHO - ancho_mapa * zoom
) / 2

desplazamiento_y = (
    ALTO - PANEL - alto_mapa * zoom
) / 2


# ============================================================
# 9. CONFIGURAR LA POSICION Y ANIMACION DEL NPC
# ============================================================

# La posicion del NPC se guarda en coordenadas del mapa,
# no en coordenadas de la ventana.
#
# npc_x representa el centro horizontal de sus pies.
# npc_y representa la posicion vertical de sus pies.

npc_x = 450
npc_y = 450
resto_movimiento = 0.0
sentido_movimiento = (0, 0)
# Rastro de esta ejecucion: un pixel amarillo por centro visitado.
# Incluye el nodo inicial y no modifica el mapa ni la transitabilidad.
capa_rastro = pygame.Surface((ancho_mapa, alto_mapa), pygame.SRCALPHA)
capa_rastro.fill((0, 0, 0, 0))
rastro_escalado = None
rastro_modificado = True

direccion_npc = "abajo"
indice_frame_npc = 0
tiempo_animacion_npc = 0.0
moviendo_npc = False

# Se muestra desde el inicio. La tecla H permite ocultarlo/mostrarlo.
mostrar_hitbox_pies = True


# ============================================================
# 10. ACTUALIZAR LA VISTA DEL MAPA
# ============================================================

def actualizar_vista():
    global mapa_escalado

    if mostrar_posiciones_validas:
        superficie = imagen_posiciones_validas
    elif modo == 0:
        superficie = imagen_original
    elif modo == 3:
        superficie = imagen_transitabilidad
    else:
        superficie = imagen_matriz

    nuevo_ancho = max(
        1,
        int(ancho_mapa * zoom)
    )

    nuevo_alto = max(
        1,
        int(alto_mapa * zoom)
    )

    # Escalado sin suavizado para conservar los pixeles.
    mapa_escalado = pygame.transform.scale(
        superficie,
        (nuevo_ancho, nuevo_alto)
    )


def centrar_mapa():
    global zoom
    global desplazamiento_x
    global desplazamiento_y

    zoom = zoom_minimo

    desplazamiento_x = (
        ANCHO - ancho_mapa * zoom
    ) / 2

    desplazamiento_y = (
        ALTO - PANEL - alto_mapa * zoom
    ) / 2

    actualizar_vista()


actualizar_vista()


# ============================================================
# 11. DIBUJAR LA CUADRICULA
# ============================================================

def dibujar_cuadricula():

    if modo != 2 and not mostrar_rejilla:
        return

    # Evitar una cuadrícula demasiado densa cuando el mapa
    # está alejado.
    if zoom < 2:
        return

    if zoom >= 3:
        paso = 1
    else:
        paso = 4

    columna_inicio = max(
        0,
        int(-desplazamiento_x / zoom)
    )

    columna_final = min(
        ancho_mapa,
        int((ANCHO - desplazamiento_x) / zoom) + 1
    )

    fila_inicio = max(
        0,
        int(-desplazamiento_y / zoom)
    )

    fila_final = min(
        alto_mapa,
        int((ALTO - PANEL - desplazamiento_y) / zoom) + 1
    )

    y1 = max(0, int(desplazamiento_y))
    y2 = min(
        ALTO - PANEL,
        int(desplazamiento_y + alto_mapa * zoom)
    )

    x1 = max(0, int(desplazamiento_x))
    x2 = min(
        ANCHO,
        int(desplazamiento_x + ancho_mapa * zoom)
    )

    for columna in range(
        (columna_inicio // paso) * paso,
        columna_final + 1,
        paso
    ):

        x = int(
            desplazamiento_x + columna * zoom
        )

        pygame.draw.line(
            pantalla,
            (20, 20, 20),
            (x, y1),
            (x, y2),
            1
        )

    for fila in range(
        (fila_inicio // paso) * paso,
        fila_final + 1,
        paso
    ):

        y = int(
            desplazamiento_y + fila * zoom
        )

        pygame.draw.line(
            pantalla,
            (20, 20, 20),
            (x1, y),
            (x2, y),
            1
        )


# ============================================================
# 12. ACTUALIZAR EL MOVIMIENTO DEL NPC
# ============================================================

# Seguimiento visual sobre los desplazamientos existentes, sin otra camara.
seguimiento_camara = False
encuadrando_npc = False
progreso_visual = 0.0


def detener_seguimiento():
    global seguimiento_camara, encuadrando_npc, progreso_visual
    global arrastrando, clic_inicial
    seguimiento_camara = encuadrando_npc = False
    progreso_visual = 0.0
    arrastrando = False
    clic_inicial = None


def centro_visual_mundo():
    if seguimiento_camara and ruta_encontrada:
        i = min(int(progreso_visual), len(ruta_encontrada)-1)
        j = min(i+1, len(ruta_encontrada)-1)
        fraccion = progreso_visual-i
        a, b = ruta_encontrada[i], ruta_encontrada[j]
        # Interpolar sobre la ruta: no cortar esquinas con una diagonal.
        return (a[0]+(b[0]-a[0])*fraccion, a[1]+(b[1]-a[1])*fraccion)
    return centro_hitbox()


def centro_pies_pantalla():
    if seguimiento_camara and not encuadrando_npc:
        return ANCHO/2, (ALTO-PANEL)/2
    x,y = centro_visual_mundo()
    sx = mapa_escalado.get_width()/ancho_mapa
    sy = mapa_escalado.get_height()/alto_mapa
    return int(desplazamiento_x)+(x+.5)*sx, int(desplazamiento_y)+(y+.5)*sy


def actualizar_seguimiento(dt):
    global desplazamiento_x, desplazamiento_y, encuadrando_npc
    global progreso_visual, seguimiento_camara
    if not seguimiento_camara or not ruta_encontrada:
        return
    factor = 1-math.exp(-18*max(0,dt))
    if not encuadrando_npc:
        progreso_visual += (indice_ruta-progreso_visual)*factor
        if not animando and abs(indice_ruta-progreso_visual)<0.01:
            progreso_visual = float(indice_ruta)
    x,y = centro_visual_mundo()
    sx = mapa_escalado.get_width()/ancho_mapa
    sy = mapa_escalado.get_height()/alto_mapa
    destino_x = ANCHO/2-(x+.5)*sx
    destino_y = (ALTO-PANEL)/2-(y+.5)*sy
    if encuadrando_npc:
        # Transicion inicial con NPC quieto: iniciar recorrido ya centrado.
        desplazamiento_x += (destino_x-desplazamiento_x)*factor
        desplazamiento_y += (destino_y-desplazamiento_y)*factor
        if max(abs(destino_x-desplazamiento_x),abs(destino_y-desplazamiento_y))<0.1:
            desplazamiento_x,desplazamiento_y = destino_x,destino_y
            encuadrando_npc = False
    else:
        desplazamiento_x,desplazamiento_y = destino_x,destino_y
        # Sin limitar al borde: se admite fondo exterior para centrar los pies.
        if not animando and progreso_visual == float(indice_ruta):
            seguimiento_camara = False


def actualizar_npc(dt):
    global animando, indice_ruta, acumulado_ruta, moviendo_npc
    global direccion_npc, indice_frame_npc, tiempo_animacion_npc, mensaje
    global pasos_desde_obstaculo
    caminaba = moviendo_npc
    moviendo_npc = False
    # Durante una replanificacion el NPC queda quieto (animacion idle).
    if animando and not pausa_replan:
        sesion["t_animacion"] += dt
        acumulado_ruta += VELOCIDAD_NPC * dt
        while acumulado_ruta >= 1 and indice_ruta < len(ruta_encontrada) - 1:
            # Sensor: si hay un bloqueo dentro del radio de deteccion, el NPC se
            # detiene aqui y gestionar_deteccion() replanifica en este cuadro.
            if gestor_obstaculos.obstaculos and detectar_obstaculo_cercano() is not None:
                break
            x, y = centro_hitbox()
            nx, ny = ruta_encontrada[indice_ruta + 1]
            dx, dy = nx - x, ny - y
            if abs(dx) + abs(dy) != 1 or not es_posicion_valida(nx, ny):
                animando = False
                mensaje = "Recorrido detenido: paso no valido."
                sesion["resultado"] = "Interrumpido: paso no valido"
                break
            mover_npc_con_colisiones(dx, dy, 1)
            if centro_hitbox() != (nx, ny):
                animando = False
                mensaje = "Recorrido detenido por colision."
                sesion["resultado"] = "Interrumpido: colision"
                break
            direccion_npc = ("derecha" if dx > 0 else "izquierda" if dx < 0
                             else "abajo" if dy > 0 else "arriba")
            indice_ruta += 1
            acumulado_ruta -= 1
            sesion["pasos"] += 1
            pasos_desde_obstaculo += 1
        if indice_ruta == len(ruta_encontrada) - 1:
            animando = False
            mensaje = "Destino alcanzado."
            sesion["resultado"] = "Destino alcanzado"
            sesion["longitud_final"] = sesion["pasos"]
        moviendo_npc = animando
    if caminaba != moviendo_npc:
        indice_frame_npc = 0
        tiempo_animacion_npc = 0.0
    tiempo_animacion_npc += dt
    intervalo = INTERVALO_ANIMACION if moviendo_npc else INTERVALO_IDLE
    while tiempo_animacion_npc >= intervalo:
        indice_frame_npc = (indice_frame_npc + 1) % 4
        tiempo_animacion_npc -= intervalo


# ============================================================
# 13. DIBUJAR EL NPC Y EL RECTANGULO DE SUS PIES
# ============================================================

def dibujar_npc():
    if inicio_busqueda is None:
        return

    # Cuando camina usamos la fila de la dirección correspondiente.
    # Cuando está quieto usamos la quinta fila (Idle).
    if moviendo_npc:
        frame = sprites_npc[direccion_npc][indice_frame_npc]
    else:
        frame = sprites_idle[indice_frame_npc]

    # El tamaño del personaje cambia con el zoom.
    ancho = max(
        1,
        int(ANCHO_NPC * zoom)
    )

    alto = max(
        1,
        int(ALTO_NPC * zoom)
    )

    # El sprite se amplía/reduce solo para visualizarlo en pantalla.
    # Su tamaño original sigue siendo 32x48 píxeles.
    frame_escalado = pygame.transform.scale(
        frame,
        (ancho, alto)
    )

    centro_x, centro_y = centro_pies_pantalla()
    # El centro geometrico de los 7 pixeles esta a 3.5 px del borde inferior.
    escala_y = mapa_escalado.get_height()/alto_mapa
    posicion_x = round(centro_x-ancho/2)
    posicion_y = round(centro_y+(ALTO_HITBOX_PIES/2)*escala_y-alto)

    pantalla.blit(
        frame_escalado,
        (posicion_x, posicion_y)
    )


def dibujar_hitbox_pies():

    if inicio_busqueda is None or not mostrar_hitbox_pies:
        return

    centro_x, centro_y = centro_pies_pantalla()
    sx = mapa_escalado.get_width()/ancho_mapa
    sy = mapa_escalado.get_height()/alto_mapa
    izquierda = round(centro_x-ANCHO_HITBOX_PIES*sx/2)
    arriba = round(centro_y-ALTO_HITBOX_PIES*sy/2)
    derecha = round(centro_x+ANCHO_HITBOX_PIES*sx/2)
    abajo = round(centro_y+ALTO_HITBOX_PIES*sy/2)
    ancho, alto = max(1,derecha-izquierda), max(1,abajo-arriba)
    rect_pies = pygame.Rect(izquierda, arriba, ancho, alto)

    # Relleno rojo semitransparente para distinguir la zona.
    relleno = pygame.Surface((ancho, alto), pygame.SRCALPHA)
    relleno.fill((255, 40, 40, 65))
    pantalla.blit(relleno, rect_pies.topleft)

    # Borde visible de la hitbox real.
    grosor = max(1, int(2 * zoom))
    pygame.draw.rect(
        pantalla,
        (255, 70, 70),
        rect_pies,
        grosor
    )


# Integracion de BFS/A*: misma cola, relajacion y reconstruccion del
# modulo logica_pathfinding.py, consultando el grafo implicito existente.
def heuristica_manhattan(nodo, objetivo):
    return abs(nodo[0] - objetivo[0]) + abs(nodo[1] - objetivo[1])


def buscar_ruta(inicio, objetivo, algoritmo, lote=LOTE_EXPANSIONES):
    """Generador para mantener la ventana activa durante la busqueda.

    Descubiertos: nodos insertados por primera vez (incluye inicio).
    Expandidos: nodos cuyos vecinos se consultan (excluye objetivo).
    Tiempo: preparacion, busqueda y reconstruccion; excluye dibujo/esperas.
    Arrays compactos guardan predecesores/costes, nunca aristas del grafo.
    """
    reloj_busqueda = perf_counter()
    tiempo = 0.0
    if not es_posicion_valida(*inicio) or not es_posicion_valida(*objetivo):
        return dict(ruta=None, descubiertos=0, expandidos=0,
                    tiempo=perf_counter()-reloj_busqueda, estado="Puntos invalidos")
    alto, ancho = matriz_posiciones_validas.shape
    total = alto * ancho
    anterior = np.full(total, -1, dtype=np.int32)
    origen = inicio[1] * ancho + inicio[0]
    meta = objetivo[1] * ancho + objetivo[0]
    anterior[origen] = origen
    es_astar = algoritmo == "A*"
    costos = np.full(total, -1, dtype=np.int32) if es_astar else None
    if es_astar:
        costos[origen] = 0
        pendientes = [(heuristica_manhattan(inicio, objetivo), 0, origen)]
    else:
        pendientes = deque([origen])
    descubiertos, expandidos, operaciones = 1, 0, 0
    encontrado = False
    while pendientes:
        if es_astar:
            _, costo_actual, actual = heappop(pendientes)
            if costo_actual != costos[actual]:
                continue
        else:
            actual = pendientes.popleft()
        if actual == meta:
            encontrado = True
            break
        expandidos += 1
        y, x = divmod(actual, ancho)
        for nx, ny in obtener_vecinos(x, y):
            vecino = ny * ancho + nx
            nuevo = anterior[vecino] == -1
            if es_astar:
                nuevo_costo = costo_actual + 1
                if not nuevo and nuevo_costo >= costos[vecino]:
                    continue
                costos[vecino] = nuevo_costo
                anterior[vecino] = actual
                heappush(pendientes, (nuevo_costo + heuristica_manhattan((nx, ny), objetivo),
                                      nuevo_costo, vecino))
            elif nuevo:
                anterior[vecino] = actual
                pendientes.append(vecino)
            else:
                continue
            if nuevo:
                descubiertos += 1
        operaciones += 1
        if operaciones % lote == 0:
            tiempo += perf_counter() - reloj_busqueda
            yield dict(descubiertos=descubiertos, expandidos=expandidos,
                       tiempo=tiempo, estado="Buscando")
            reloj_busqueda = perf_counter()
    ruta = None
    if encontrado:
        ruta = []
        nodo = meta
        while True:
            y, x = divmod(nodo, ancho)
            ruta.append((x, y))
            if nodo == origen:
                break
            nodo = int(anterior[nodo])
        ruta.reverse()
    tiempo += perf_counter() - reloj_busqueda
    return dict(ruta=ruta, descubiertos=descubiertos, expandidos=expandidos,
                tiempo=tiempo, estado="Ruta encontrada" if encontrado else "Sin camino")


def bfs_busqueda(inicio, objetivo, lote=LOTE_EXPANSIONES):
    return buscar_ruta(inicio, objetivo, "BFS", lote)


def astar_busqueda(inicio, objetivo, lote=LOTE_EXPANSIONES):
    return buscar_ruta(inicio, objetivo, "A*", lote)


def mouse_a_nodo(pos):
    if not (0 <= pos[0] < ANCHO and 0 <= pos[1] < ALTO-PANEL):
        return None
    # Mismos origen y dimensiones enteras usados al dibujar mapa_escalado.
    x = math.floor((pos[0]-int(desplazamiento_x))*ancho_mapa/mapa_escalado.get_width())
    y = math.floor((pos[1]-int(desplazamiento_y))*alto_mapa/mapa_escalado.get_height())
    return (x, y) if es_posicion_valida(x, y) else None


def ubicar_en_inicio():
    detener_seguimiento()
    global npc_x, npc_y, resto_movimiento, sentido_movimiento
    global indice_ruta, acumulado_ruta, rastro_modificado
    global moviendo_npc, indice_frame_npc, tiempo_animacion_npc
    npc_x, y = inicio_busqueda
    npc_y = y + ALTO_HITBOX_PIES//2 + 1
    resto_movimiento = acumulado_ruta = 0.0
    sentido_movimiento = (0, 0)
    indice_ruta = 0
    moviendo_npc = False
    indice_frame_npc = 0
    tiempo_animacion_npc = 0.0
    capa_rastro.fill((0,0,0,0))
    rastro_modificado = True
    marcar_rastro(*inicio_busqueda)


def reiniciar_busqueda():
    detener_seguimiento()
    global inicio_busqueda, destino_busqueda, tarea_busqueda, ruta_encontrada
    global animando, mensaje, estadisticas, rastro_modificado, ruta_escalada
    global moviendo_npc, comparando, tarea_comparacion, pausa_replan
    global replan_actual, sesion, algoritmo_activo, ruta_inicial, ruta_np
    global pasos_desde_obstaculo
    if tarea_busqueda is not None:
        tarea_busqueda.close()
    if tarea_comparacion is not None:
        tarea_comparacion.close()
    tarea_comparacion, comparando = None, False
    pausa_replan, replan_actual = False, None
    limpiar_mundo_dinamico()
    inicio_busqueda = destino_busqueda = tarea_busqueda = None
    ruta_encontrada = ruta_inicial = ruta_np = None
    algoritmo_activo = None
    sesion = nueva_sesion(None)
    pasos_desde_obstaculo = 0
    estadisticas = {}
    animando = moviendo_npc = False
    capa_rastro.fill((0,0,0,0))
    capa_ruta.fill((0,0,0,0))
    rastro_modificado = True
    ruta_escalada = None
    mensaje = "Selecciona el inicio con un clic y despues el destino."


def seleccionar_punto(pos):
    global inicio_busqueda, destino_busqueda, mensaje
    if tarea_busqueda is not None or animando or comparando:
        return
    nodo = mouse_a_nodo(pos)
    if nodo is None:
        mensaje = "Posicion invalida: la hitbox completa debe caber en terreno libre."
    elif inicio_busqueda is None:
        inicio_busqueda = nodo
        ubicar_en_inicio()
        mensaje = "Inicio seleccionado. Ahora selecciona el destino."
    elif destino_busqueda is None:
        destino_busqueda = nodo
        mensaje = "Puntos listos. Ejecuta BFS o A*."
    else:
        mensaje = "Pulsa Reiniciar para seleccionar otros puntos."


def ejecutar_busqueda(algoritmo):
    global tarea_busqueda, animando, ruta_encontrada, estadisticas, mensaje, ruta_escalada
    global algoritmo_activo, sesion, ruta_inicial, ruta_np, pausa_replan, replan_actual
    if inicio_busqueda is None or destino_busqueda is None or tarea_busqueda is not None or comparando:
        return
    animando = False
    # Cada ejecucion parte del mapa limpio: mismas condiciones iniciales.
    limpiar_mundo_dinamico()
    pausa_replan, replan_actual = False, None
    ubicar_en_inicio()
    ruta_encontrada = ruta_inicial = ruta_np = None
    capa_ruta.fill((0,0,0,0))
    ruta_escalada = None
    algoritmo_activo = algoritmo
    gestor_obstaculos.rng.seed(cfg_semilla)
    sesion = nueva_sesion(algoritmo)
    resultados_sesion[algoritmo] = sesion
    estadisticas = dict(algoritmo=algoritmo, descubiertos=0, expandidos=0,
                        tiempo=0.0, estado="Buscando")
    tarea_busqueda = (bfs_busqueda if algoritmo == "BFS" else astar_busqueda)(
        inicio_busqueda, destino_busqueda)
    mensaje = "Buscando... puedes mover la camara o reiniciar."


def avanzar_busqueda():
    global tarea_busqueda, ruta_encontrada, mensaje, ruta_escalada, ruta_inicial
    if tarea_busqueda is None:
        return
    try:
        estadisticas.update(next(tarea_busqueda))
    except StopIteration as fin:
        resultado = fin.value
        tarea_busqueda = None
        if replan_actual is not None:      # termino una replanificacion
            finalizar_replanificacion(resultado)
            return
        ruta = resultado.pop("ruta")
        estadisticas.update(resultado)
        mensaje = estadisticas["estado"]
        if ruta is not None:
            instalar_ruta(ruta)
            ruta_inicial = list(ruta)
            registrar_inicial(sesion, estadisticas, len(ruta) - 1)
            mensaje += ". Pulsa Animar recorrido."
        else:
            ruta_encontrada = None
            sesion["resultado"] = "Sin camino"
        ruta_escalada = None


def animar_recorrido():
    global animando, mensaje, seguimiento_camara, encuadrando_npc, progreso_visual
    global zoom
    if tarea_busqueda is None and ruta_encontrada is not None and not animando and not comparando:
        restaurar_escenario_inicial()   # mapa limpio + ruta inicial + misma semilla
        ubicar_en_inicio()
        zoom = min(zoom_maximo, max(zoom, ZOOM_SEGUIMIENTO))
        actualizar_vista()
        animando = len(ruta_encontrada) > 1
        seguimiento_camara = True
        encuadrando_npc = True
        progreso_visual = 0.0
        mensaje = "Recorriendo ruta..." if animando else "El inicio ya es el destino."


def dibujar_resultado():
    global ruta_escalada, descartada_escalada
    if descartada_escalada is None or descartada_escalada.get_size() != mapa_escalado.get_size():
        descartada_escalada = pygame.transform.scale(capa_descartada, mapa_escalado.get_size())
    pantalla.blit(descartada_escalada, (int(desplazamiento_x), int(desplazamiento_y)))
    if ruta_encontrada is not None:
        if ruta_escalada is None or ruta_escalada.get_size() != mapa_escalado.get_size():
            ruta_escalada = pygame.transform.scale(capa_ruta, mapa_escalado.get_size())
        pantalla.blit(ruta_escalada, (int(desplazamiento_x), int(desplazamiento_y)))
    for nodo, color, etiqueta in ((inicio_busqueda,(50,255,110),"Inicio"),
                                  (destino_busqueda,(255,80,240),"Destino")):
        if nodo is not None:
            x = int(desplazamiento_x) + (nodo[0]+.5)*mapa_escalado.get_width()/ancho_mapa
            y = int(desplazamiento_y) + (nodo[1]+.5)*mapa_escalado.get_height()/alto_mapa
            pygame.draw.circle(pantalla, (0,0,0), (round(x),round(y)), 7)
            pygame.draw.circle(pantalla, color, (round(x),round(y)), 5)
            pantalla.blit(fuente.render(etiqueta, True, color), (x+8,y-15))


# Visualizador local: consulta la matriz existente y no almacena el grafo.
def crear_imagen_subgrafo(x, y, ancho, alto):
    filas, columnas = matriz_posiciones_validas.shape
    if x < 0 or y < 0 or ancho <= 0 or alto <= 0:
        raise ValueError("X/Y deben ser >= 0; ancho/alto deben ser mayores que 0.")
    if x + ancho > columnas or y + alto > filas:
        raise ValueError(f"La region debe quedar dentro de {columnas} x {filas}.")
    nodos = matriz_posiciones_validas[y:y+alto, x:x+ancho] == 1
    # Derecha y abajo equivalen a las cuatro vecindades sin duplicar aristas.
    horizontales = nodos[:, :-1] & nodos[:, 1:]
    verticales = nodos[:-1, :] & nodos[1:, :]
    cantidad_nodos = int(np.count_nonzero(nodos))
    cantidad_aristas = int(np.count_nonzero(horizontales) + np.count_nonzero(verticales))
    paso = min(14, max(2, 700 // max(ancho, alto)))
    fondo = imagen_original.subsurface(pygame.Rect(x, y, ancho, alto))
    imagen = pygame.transform.scale(fondo, (ancho*paso, alto*paso))
    for o in gestor_obstaculos.obstaculos:  # obstaculos dinamicos visibles
        if o.x < x+ancho and o.x+o.ancho > x and o.y < y+alto and o.y+o.alto > y:
            imagen.blit(pygame.transform.scale(
                o.sprite, (o.ancho*paso, o.alto*paso)), ((o.x-x)*paso, (o.y-y)*paso))
    pixeles = pygame.surfarray.pixels3d(imagen)
    centro = paso // 2
    fy, fx = np.nonzero(horizontales)
    vy, vx = np.nonzero(verticales)
    # Cada asignacion pinta simultaneamente todas las aristas de un grupo.
    for offset in range(paso + 1):
        pixeles[fx*paso+centro+offset, fy*paso+centro] = (245,35,35)
        pixeles[vx*paso+centro, vy*paso+centro+offset] = (245,35,35)
    ny, nx = np.nonzero(nodos)
    radio = 1 if paso >= 6 else 0
    for dy in range(-radio, radio+1):
        for dx in range(-radio, radio+1):
            if dx*dx+dy*dy <= radio*radio:
                pixeles[nx*paso+centro+dx, ny*paso+centro+dy] = (25,90,255)
    del pixeles  # Liberar el bloqueo antes de mostrar la superficie.
    return imagen, cantidad_nodos, cantidad_aristas


class VisualizadorSubgrafo:
    """Ventana secundaria. Cerrar esta ventana no llama a pygame.quit()."""
    def __init__(self):
        self.ventana = pygame.Window("Configurar subgrafo", size=(700,430))
        self.campos = ["450", "400", "50", "50"]
        self.activo = 0
        self.reemplazar = True
        self.error = ""
        self.imagen = None
        self.rects = [pygame.Rect(270,65+i*55,200,36) for i in range(4)]
        self.confirmar = pygame.Rect(270,300,200,38)
        self.volver = pygame.Rect(15,15,170,32)
        self.dibujar()

    def generar(self):
        try:
            valores = [int(c) for c in self.campos]
            imagen, nodos, aristas = crear_imagen_subgrafo(*valores)
        except ValueError as error:
            self.error = str(error)
            self.dibujar()
            return
        self.imagen = imagen
        self.region = valores
        self.nodos, self.aristas = nodos, aristas
        self.ventana.title = "Subgrafo del mapa - nodos y conexiones"
        self.ventana.size = (960,850)
        factor = min(920/imagen.get_width(), 700/imagen.get_height(), 1)
        self.presentacion = pygame.transform.scale(imagen,
            (max(1,int(imagen.get_width()*factor)), max(1,int(imagen.get_height()*factor))))
        self.dibujar()

    def dibujar(self):
        superficie = self.ventana.get_surface()
        superficie.fill((24,29,35))
        if self.imagen is None:
            textos = [("Region en coordenadas del mapa (x = columna, y = fila)",(20,20)),
                      ("Clic o TAB: campo | Escribir: valor | ENTER: visualizar | ESC: cerrar",(20,360)),
                      (self.error,(20,390))]
            for i,nombre in enumerate(("X inicial", "Y inicial", "Ancho", "Alto")):
                superficie.blit(fuente.render(nombre,True,(230,230,230)),(130,75+i*55))
                rect = self.rects[i]
                pygame.draw.rect(superficie,(50,60,70),rect)
                pygame.draw.rect(superficie,(80,180,255) if i==self.activo else (100,110,120),rect,2)
                superficie.blit(fuente.render(self.campos[i],True,(255,255,255)),(rect.x+10,rect.y+9))
            pygame.draw.rect(superficie,(45,105,145),self.confirmar,border_radius=4)
            superficie.blit(fuente.render("Visualizar",True,(255,255,255)),(320,310))
        else:
            x,y,w,h = self.region
            pygame.draw.rect(superficie,(45,105,145),self.volver,border_radius=4)
            superficie.blit(fuente.render("Cambiar region",True,(255,255,255)),(30,23))
            textos = [(f"Origen: ({x}, {y}) | Region: {w} x {h} | Nodos: {self.nodos:,} | Aristas: {self.aristas:,}",(15,60)),
                      ("Azul: nodos validos | Rojo: conexiones internas | Fondo: mapa original",(15,82)),
                      ("Coordenadas: X crece a la derecha; Y hacia abajo. ESC cierra solo esta ventana.",(15,815))]
            superficie.blit(self.presentacion,((960-self.presentacion.get_width())//2,105))
        for texto,pos in textos:
            superficie.blit(fuente.render(texto,True,(230,230,230)),pos)
        self.ventana.flip()

    def evento(self, evento):
        if evento.type == pygame.WINDOWCLOSE or (evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE):
            self.ventana.destroy()
            return False
        if evento.type == pygame.WINDOWEXPOSED:
            self.dibujar()
        if self.imagen is not None:
            if evento.type == pygame.MOUSEBUTTONDOWN and evento.button==1 and self.volver.collidepoint(evento.pos):
                self.imagen = None
                self.error = ""
                self.ventana.size = (700,430)
                self.ventana.title = "Configurar subgrafo"
                self.dibujar()
            return True
        if evento.type == pygame.MOUSEBUTTONDOWN and evento.button==1:
            for i,rect in enumerate(self.rects):
                if rect.collidepoint(evento.pos):
                    self.activo, self.reemplazar = i, True
            if self.confirmar.collidepoint(evento.pos):
                self.generar()
                return True
        if evento.type == pygame.KEYDOWN:
            if evento.key in (pygame.K_RETURN,pygame.K_KP_ENTER):
                self.generar()
                return True
            if evento.key == pygame.K_TAB:
                self.activo = (self.activo+(-1 if evento.mod & pygame.KMOD_SHIFT else 1)) % 4
                self.reemplazar = True
            elif evento.key == pygame.K_BACKSPACE:
                self.campos[self.activo] = "" if self.reemplazar else self.campos[self.activo][:-1]
                self.reemplazar = False
            else:
                caracter = getattr(evento,"unicode","")
                if caracter and caracter.isascii() and caracter.isdigit():
                    valor = "" if self.reemplazar else self.campos[self.activo]
                    self.campos[self.activo] = (valor+caracter)[:6]
                    self.reemplazar = False
        self.dibujar()
        return True


visualizador_subgrafo = None
# Permite identificar eventos de la ventana principal sin recrearla.
ventana_principal = pygame.Window.from_display_module()


def abrir_subgrafo():
    global visualizador_subgrafo
    if visualizador_subgrafo is None:
        visualizador_subgrafo = VisualizadorSubgrafo()
    else:
        visualizador_subgrafo.ventana.focus()


# ============================================================
# 16. OBSTACULOS DINAMICOS, REPLANIFICACION, COMPARACION E INFORME
# ============================================================
# Flujo en vivo: aparece un obstaculo -> se actualiza la matriz efectiva solo
# en su ventana -> se comprueba (vectorizado) si bloquea el tramo pendiente de
# la ruta -> si lo bloquea, se pausa el NPC y se vuelve a ejecutar el mismo
# algoritmo desde la posicion actual hacia el destino original.

MIN_ADELANTE = 40        # Nodos minimos por delante del NPC al aparecer.
ALCANCE_RUTA = 140       # Maximo de nodos por delante (para que sea visible).
DURACION_EFECTO = 0.8    # Segundos del destello de aparicion.


def nueva_sesion(algoritmo, origen="Animacion en vivo"):
    return dict(algoritmo=algoritmo, origen=origen, semilla=cfg_semilla,
                inicial=None, obstaculos=0, sin_efecto=0, omitidos=0,
                retirados=0, replans=0, replans_ok=0, replans_fallidas=0,
                t_busqueda=0.0, t_replan=0.0, descubiertos=0, expandidos=0,
                t_preparacion=0.0, t_animacion=0.0, pasos=0,
                longitud_final=None, resultado="--", log=[])


def registrar_inicial(ses, res, longitud):
    ses["inicial"] = dict(tiempo=res["tiempo"], descubiertos=res["descubiertos"],
                          expandidos=res["expandidos"], longitud=longitud)
    ses["t_busqueda"] = res["tiempo"]
    ses["descubiertos"] = res["descubiertos"]
    ses["expandidos"] = res["expandidos"]
    ses["longitud_final"] = longitud


def acumular_replan(ses, res, exito):
    ses["replans"] += 1
    ses["replans_ok" if exito else "replans_fallidas"] += 1
    ses["t_busqueda"] += res["tiempo"]
    ses["t_replan"] += res["tiempo"]
    ses["descubiertos"] += res["descubiertos"]
    ses["expandidos"] += res["expandidos"]


def refrescar_imagen_posiciones(region):
    """Actualiza solo la ventana afectada de la vista V (posiciones validas).
    Naranja = valida en el mapa estatico pero bloqueada por un dinamico."""
    x0, y0, x1, y1 = region
    efectiva = matriz_posiciones_validas[y0:y1, x0:x1]
    colores = np.empty((y1 - y0, x1 - x0, 3), dtype=np.uint8)
    colores[:] = (220, 55, 55)
    colores[efectiva == 1] = (35, 190, 85)
    colores[(matriz_posiciones_validas_estatica[y0:y1, x0:x1] == 1)
            & (efectiva == 0)] = (255, 150, 0)
    pixeles = pygame.surfarray.pixels3d(imagen_posiciones_validas)
    pixeles[x0:x1, y0:y1] = colores.transpose(1, 0, 2)
    del pixeles


def registrar_cambio_mapa(info, rescalar=True):
    global cantidad_validas, cantidad_invalidas, porcentaje_validas
    cantidad_validas += info["delta"]
    cantidad_invalidas = int(matriz_posiciones_validas.size) - cantidad_validas
    porcentaje_validas = 100 * cantidad_validas / matriz_posiciones_validas.size
    refrescar_imagen_posiciones(info["region"])
    if rescalar and mostrar_posiciones_validas:
        actualizar_vista()


def limpiar_mundo_dinamico():
    global descartada_escalada
    cambios = gestor_obstaculos.limpiar()
    for c in cambios:
        registrar_cambio_mapa(c, rescalar=False)
    if cambios and mostrar_posiciones_validas:
        actualizar_vista()
    efectos_aparicion.clear()
    capa_descartada.fill((0, 0, 0, 0))
    descartada_escalada = None


def instalar_ruta(ruta):
    global ruta_encontrada, ruta_np, ruta_escalada
    ruta_encontrada = ruta
    ruta_np = np.array(ruta, dtype=np.intp).reshape(-1, 2)
    capa_ruta.fill((0, 0, 0, 0))
    for nodo in ruta:
        capa_ruta.set_at(nodo, (255, 225, 0, 255))
    ruta_escalada = None


def restaurar_escenario_inicial():
    """Vuelve al mapa limpio y a la ruta inicial para poder repetir la
    animacion con las mismas condiciones (misma semilla)."""
    global pausa_replan, replan_actual, pasos_desde_obstaculo, sesion
    limpiar_mundo_dinamico()
    pausa_replan = False
    replan_actual = None
    pasos_desde_obstaculo = 0
    if ruta_inicial is not None:
        instalar_ruta(list(ruta_inicial))
    ini = sesion.get("inicial")
    nueva = nueva_sesion(algoritmo_activo)
    if ini:
        nueva["inicial"] = ini
        nueva["t_busqueda"] = ini["tiempo"]
        nueva["descubiertos"] = ini["descubiertos"]
        nueva["expandidos"] = ini["expandidos"]
        nueva["longitud_final"] = ini["longitud"]
    sesion = nueva
    resultados_sesion[algoritmo_activo] = sesion
    gestor_obstaculos.rng.seed(cfg_semilla)


def generar_obstaculo():
    """Hace aparecer un obstaculo durante la animacion. Devuelve True si se
    coloco. Es la unica puerta de entrada de obstaculos en vivo."""
    global mensaje, pasos_desde_obstaculo
    if (tarea_busqueda is not None or comparando or not animando
            or pausa_replan or encuadrando_npc or ruta_encontrada is None):
        return False
    t0 = perf_counter()
    npc = centro_hitbox()
    obs = gestor_obstaculos.proponer(
        cfg_modo, cfg_tamano, ruta_encontrada, indice_ruta, npc,
        destino_busqueda, rango=(cfg_radio_deteccion + 25, cfg_radio_deteccion + 55))
    if obs is None:
        mensaje = "No hay un lugar valido para un obstaculo en este momento."
        return False
    obs.paso = sesion["pasos"]
    info = gestor_obstaculos.colocar(obs)
    registrar_cambio_mapa(info)
    efectos_aparicion.append(dict(obs=obs, t=0.0))
    sesion["obstaculos"] += 1
    pasos_desde_obstaculo = 0
    bloqueado = gestor_obstaculos.ruta_bloqueada(ruta_np, indice_ruta)
    sesion["t_preparacion"] += perf_counter() - t0
    if bloqueado is None:
        sesion["sin_efecto"] += 1
        sesion["log"].append(dict(
            evento="sin_efecto", paso=sesion["pasos"], posicion=npc,
            obstaculo=obs.descripcion(),
            resultado="Sin efecto: la ruta sigue valida, no se recalcula"))
        mensaje = f"Obstaculo {obs.tipo} #{obs.id}: no afecta la ruta, no se recalcula."
    else:
        mensaje = (f"Aparecio {obs.tipo} #{obs.id} a {bloqueado - indice_ruta} pasos sobre la ruta. "
                   f"El NPC lo detectara a {cfg_radio_deteccion} px.")
    return True


def detectar_obstaculo_cercano():
    """Sensor del NPC: indice del primer nodo bloqueado de la ruta dentro del
    radio de deteccion (cfg_radio_deteccion nodos por delante) o None."""
    if ruta_np is None:
        return None
    tramo = ruta_np[indice_ruta + 1: indice_ruta + cfg_radio_deteccion + 2]
    if len(tramo) == 0:
        return None
    libres = gestor_obstaculos.efectiva[tramo[:, 1], tramo[:, 0]]
    if libres.all():
        return None
    return indice_ruta + 1 + int(np.argmin(libres))


def gestionar_deteccion():
    """Si el sensor ve un bloqueo cercano, pausa y replanifica desde aqui."""
    global mensaje
    if not (animando and not pausa_replan and not encuadrando_npc
            and tarea_busqueda is None and not comparando
            and gestor_obstaculos.obstaculos):
        return
    idx = detectar_obstaculo_cercano()
    if idx is None:
        return
    nx, ny = ruta_encontrada[idx]
    obs = next((o for o in gestor_obstaculos.obstaculos
                if o.region[0] <= nx < o.region[2] and o.region[1] <= ny < o.region[3]),
               gestor_obstaculos.obstaculos[-1])
    iniciar_replanificacion(obs, idx)
    mensaje = (f"NPC detecta {obs.tipo} #{obs.id} a {idx - indice_ruta} pasos. "
               f"Pausa y replanificacion con {algoritmo_activo} desde {centro_hitbox()}...")


def iniciar_replanificacion(obstaculo, indice_bloqueo):
    global tarea_busqueda, pausa_replan, replan_actual, mensaje, moviendo_npc
    pos = centro_hitbox()
    replan_actual = dict(
        obstaculo=obstaculo, paso=sesion["pasos"], posicion=pos,
        bloqueado_en=indice_bloqueo,
        restante_anterior=len(ruta_encontrada) - 1 - indice_ruta,
        ruta_vieja=list(ruta_encontrada[indice_ruta:]))
    pausa_replan = True
    moviendo_npc = False
    estadisticas.update(algoritmo=algoritmo_activo, descubiertos=0,
                        expandidos=0, tiempo=0.0, estado="Replanificando")
    tarea_busqueda = buscar_ruta(pos, destino_busqueda, algoritmo_activo,
                                 LOTE_EXPANSIONES)
    mensaje = (f"Obstaculo {obstaculo.tipo} #{obstaculo.id} bloquea la ruta. "
               f"Pausa y replanificacion con {algoritmo_activo} desde {pos}...")


def finalizar_replanificacion(resultado):
    global replan_actual, pausa_replan, animando, mensaje, indice_ruta
    global progreso_visual, descartada_escalada
    info = replan_actual
    replan_actual = None
    ruta = resultado.pop("ruta")
    estadisticas.update(resultado)
    exito = ruta is not None
    acumular_replan(sesion, resultado, exito)
    entrada = dict(
        evento="replan", num=sesion["replans"], paso=info["paso"],
        posicion=info["posicion"], obstaculo=info["obstaculo"].descripcion(),
        tiempo=resultado["tiempo"], descubiertos=resultado["descubiertos"],
        expandidos=resultado["expandidos"],
        restante_anterior=info["restante_anterior"],
        longitud_nueva=(len(ruta) - 1) if exito else None, resultado="")
    if exito:
        nueva = set(ruta)
        for nodo in info["ruta_vieja"]:
            if nodo not in nueva:
                capa_descartada.set_at(nodo, (255, 110, 20, 235))
        descartada_escalada = None
        instalar_ruta(ruta)
        indice_ruta = 0
        progreso_visual = 0.0
        sesion["longitud_final"] = sesion["pasos"] + len(ruta) - 1
        entrada["resultado"] = "Ruta encontrada"
        mensaje = (f"Replanificacion #{sesion['replans']} ({algoritmo_activo}): "
                   f"nueva ruta de {len(ruta) - 1} movimientos. Continua el recorrido.")
    elif cfg_sin_ruta == "retirar":
        registrar_cambio_mapa(gestor_obstaculos.retirar(info["obstaculo"]))
        sesion["retirados"] += 1
        entrada["resultado"] = "Sin ruta: obstaculo retirado"
        mensaje = ("Sin ruta posible con ese obstaculo: se retira y el NPC "
                   "continua por la ruta anterior.")
    else:
        animando = False
        sesion["resultado"] = "Sin ruta posible: recorrido detenido"
        entrada["resultado"] = "Sin ruta: recorrido detenido"
        mensaje = "Sin ruta posible hasta el destino. Recorrido detenido."
    sesion["log"].append(entrada)
    pausa_replan = False


def gestionar_aparicion_automatica():
    global pasos_desde_obstaculo
    if not (aparicion_auto and animando and not pausa_replan
            and not encuadrando_npc and tarea_busqueda is None
            and not comparando):
        return
    if sesion["obstaculos"] >= cfg_maximo or pasos_desde_obstaculo < cfg_cada_pasos:
        return
    if not generar_obstaculo():
        pasos_desde_obstaculo = max(0, cfg_cada_pasos - 20)  # reintenta pronto


# ------------------ dibujo de obstaculos ------------------

def actualizar_efectos(dt):
    for e in efectos_aparicion:
        e["t"] += dt
    efectos_aparicion[:] = [e for e in efectos_aparicion if e["t"] < DURACION_EFECTO]


def _rect_pantalla(x, y, ancho, alto):
    sx = mapa_escalado.get_width() / ancho_mapa
    sy = mapa_escalado.get_height() / alto_mapa
    return pygame.Rect(round(int(desplazamiento_x) + x * sx),
                       round(int(desplazamiento_y) + y * sy),
                       max(1, round(ancho * sx)), max(1, round(alto * sy)))


def dibujar_obstaculos(delante):
    """delante=False: obstaculos situados 'detras' de los pies del NPC;
    delante=True: los que estan mas abajo y deben taparlo."""
    if not gestor_obstaculos.obstaculos:
        return
    pie = centro_hitbox()[1] if inicio_busqueda is not None else -1
    visible = pygame.Rect(0, 0, ANCHO, ALTO - PANEL)
    for o in gestor_obstaculos.obstaculos:
        if ((o.y + o.alto) > pie) != delante:
            continue
        r = _rect_pantalla(o.x, o.y, o.ancho, o.alto)
        if not r.colliderect(visible):
            continue
        if o.cache_tamano != r.size:
            o.cache_sprite = pygame.transform.scale(o.sprite, r.size)
            o.cache_tamano = r.size
        pantalla.blit(o.cache_sprite, r.topleft)


def dibujar_zonas_bloqueo():
    """Muestra la zona inflada por la hitbox (centros de pies invalidados)."""
    if not mostrar_zonas_bloqueo:
        return
    for o in gestor_obstaculos.obstaculos:
        x0, y0, x1, y1 = o.region
        r = _rect_pantalla(x0, y0, x1 - x0, y1 - y0)
        velo = pygame.Surface(r.size, pygame.SRCALPHA)
        velo.fill((255, 40, 40, 60))
        pantalla.blit(velo, r.topleft)
        pygame.draw.rect(pantalla, (255, 80, 80), r, 1)
        pygame.draw.rect(pantalla, (255, 255, 255),
                         _rect_pantalla(*o.huella), 1)


def dibujar_efectos():
    for e in efectos_aparicion:
        o = e["obs"]
        f = e["t"] / DURACION_EFECTO
        r = _rect_pantalla(*o.huella).inflate(int(8 + 44 * f), int(8 + 44 * f))
        color = (255, int(230 - 120 * f), 80)
        pygame.draw.rect(pantalla, color, r, 2, border_radius=8)


# ------------------ comparacion justa BFS vs A* ------------------

def _buscar_progreso(inicio, objetivo, alg, texto):
    gen = buscar_ruta(inicio, objetivo, alg, LOTE_EXPANSIONES)
    while True:
        try:
            p = next(gen)
        except StopIteration as fin:
            return fin.value
        yield f"{texto} - {p['expandidos']:,} nodos expandidos"


def _simular_algoritmo(alg, inicial, guion, destino, cfg):
    """Camina virtualmente por la ruta aplicando el MISMO guion de obstaculos
    (mismos obstaculos, mismos pasos de disparo). No dibuja ni espera."""
    limpiar_mundo_dinamico()
    ses = nueva_sesion(alg, "Comparacion justa (simulada)")
    ses["semilla"] = cfg["semilla"]
    ruta = inicial["ruta"]
    registrar_inicial(ses, inicial, len(ruta) - 1)
    idx, pasos, resultado = 0, 0, "Destino alcanzado"
    for ev in guion:
        avance = ev.paso - pasos
        if avance > 0:
            if idx + avance >= len(ruta) - 1:
                break                      # llega antes de que aparezca
            idx += avance
            pasos += avance
        pos = ruta[idx]
        obs = gestor_obstaculos.instanciar_evento(ev)
        t0 = perf_counter()
        if not gestor_obstaculos.candidato_valido(*obs.huella, npc=pos, destino=destino):
            ses["omitidos"] += 1
            ses["log"].append(dict(evento="omitido", paso=pasos, posicion=pos,
                                   obstaculo=obs.descripcion(),
                                   resultado="Omitido: demasiado cerca del NPC"))
            continue
        registrar_cambio_mapa(gestor_obstaculos.colocar(obs), rescalar=False)
        obs.paso = pasos
        ses["obstaculos"] += 1
        bloqueado = gestor_obstaculos.ruta_bloqueada(
            np.array(ruta, dtype=np.intp).reshape(-1, 2), idx)
        ses["t_preparacion"] += perf_counter() - t0
        if bloqueado is None:
            ses["sin_efecto"] += 1
            ses["log"].append(dict(evento="sin_efecto", paso=pasos, posicion=pos,
                                   obstaculo=obs.descripcion(),
                                   resultado="Sin efecto: no se recalcula"))
            continue
        avance_det = max(0, (bloqueado - idx) - cfg["radio"])
        idx += avance_det
        pasos += avance_det
        pos = ruta[idx]
        res = yield from _buscar_progreso(
            pos, destino, alg,
            f"Comparando {alg}: replanificacion {ses['replans'] + 1}")
        nueva = res.pop("ruta")
        acumular_replan(ses, res, nueva is not None)
        entrada = dict(evento="replan", num=ses["replans"], paso=pasos,
                       posicion=pos, obstaculo=obs.descripcion(),
                       tiempo=res["tiempo"], descubiertos=res["descubiertos"],
                       expandidos=res["expandidos"],
                       restante_anterior=len(ruta) - 1 - idx,
                       longitud_nueva=(len(nueva) - 1) if nueva else None,
                       resultado="Ruta encontrada")
        if nueva is not None:
            ruta, idx = nueva, 0
        elif cfg["politica"] == "retirar":
            registrar_cambio_mapa(gestor_obstaculos.retirar(obs), rescalar=False)
            ses["retirados"] += 1
            entrada["resultado"] = "Sin ruta: obstaculo retirado"
        else:
            entrada["resultado"] = "Sin ruta: recorrido detenido"
            resultado = "Sin ruta posible: recorrido detenido"
            ses["log"].append(entrada)
            break
        ses["log"].append(entrada)
    if resultado == "Destino alcanzado":
        pasos += len(ruta) - 1 - idx
    ses["pasos"], ses["longitud_final"] = pasos, pasos
    ses["resultado"] = resultado
    ses["t_animacion"] = None            # simulado: no hay animacion
    return ses


def generador_comparacion(inicio, destino, cfg):
    gestor_obstaculos.rng.seed(cfg["semilla"])
    iniciales = {}
    for alg in ("BFS", "A*"):
        res = yield from _buscar_progreso(
            inicio, destino, alg, f"Comparando: busqueda inicial {alg}")
        if res["ruta"] is None:
            return f"Comparacion cancelada: {alg} no encuentra ruta inicial."
        iniciales[alg] = res
    guion = gestor_obstaculos.crear_guion(
        [iniciales["BFS"]["ruta"], iniciales["A*"]["ruta"]],
        cfg["cantidad"], cfg["tamano"], destino)
    for alg in ("BFS", "A*"):
        resultados_sesion[alg] = yield from _simular_algoritmo(
            alg, iniciales[alg], guion, destino, cfg)
    limpiar_mundo_dinamico()
    return (f"Comparacion lista: {len(guion)} obstaculos identicos para "
            "ambos algoritmos. Revisa el informe (I).")


def iniciar_comparacion():
    global comparando, tarea_comparacion, animando, ruta_encontrada
    global ruta_escalada, mensaje, pausa_replan, replan_actual
    if inicio_busqueda is None or destino_busqueda is None or comparando or tarea_busqueda is not None:
        return
    animando = pausa_replan = False
    replan_actual = None
    limpiar_mundo_dinamico()
    ubicar_en_inicio()
    ruta_encontrada = None
    capa_ruta.fill((0, 0, 0, 0))
    ruta_escalada = None
    comparando = True
    cfg = dict(cantidad=cfg_maximo, tamano=cfg_tamano, semilla=cfg_semilla,
               politica=cfg_sin_ruta, radio=cfg_radio_deteccion)
    tarea_comparacion = generador_comparacion(inicio_busqueda, destino_busqueda, cfg)
    mensaje = "Comparando BFS y A* con los mismos obstaculos..."


def avanzar_comparacion():
    global comparando, tarea_comparacion, mensaje
    if tarea_comparacion is None:
        return
    try:
        mensaje = next(tarea_comparacion)
    except StopIteration as fin:
        tarea_comparacion, comparando = None, False
        mensaje = fin.value or "Comparacion terminada."
        abrir_informe()


# ------------------ informe ------------------

def ms(t):
    return "--" if t is None else f"{t * 1000:.1f} ms"


def linea_log(e):
    if e["evento"] == "replan":
        nueva = "-" if e["longitud_nueva"] is None else e["longitud_nueva"]
        return (f"#{e['num']} p{e['paso']} {e['obstaculo']} -> {e['resultado']} | "
                f"{e['tiempo'] * 1000:.1f}ms d{e['descubiertos']:,} "
                f"e{e['expandidos']:,} L{e['restante_anterior']}->{nueva}")
    return f"p{e['paso']} {e['obstaculo']} -> {e['resultado']}"


def filas_informe():
    s = {a: resultados_sesion.get(a) for a in ("BFS", "A*")}

    def col(f):
        return [("--" if s[a] is None else f(s[a])) for a in ("BFS", "A*")]
    ini = lambda q, f: (lambda x: "--" if x["inicial"] is None else f(x["inicial"]))(q)
    return [
        ("Origen de los datos", col(lambda x: x["origen"])),
        ("Resultado", col(lambda x: x["resultado"])),
        ("Semilla de obstaculos", col(lambda x: str(x["semilla"]))),
        ("Busqueda inicial: tiempo", col(lambda x: ini(x, lambda i: ms(i["tiempo"])))),
        ("  descubiertos / expandidos",
         col(lambda x: ini(x, lambda i: f"{i['descubiertos']:,} / {i['expandidos']:,}"))),
        ("  longitud de ruta (movimientos)", col(lambda x: ini(x, lambda i: str(i["longitud"])))),
        ("Obstaculos dinamicos generados", col(lambda x: str(x["obstaculos"]))),
        ("  sin efecto (no se recalculo)", col(lambda x: str(x["sin_efecto"]))),
        ("  omitidos / retirados por bloqueo total",
         col(lambda x: f"{x['omitidos']} / {x['retirados']}")),
        ("Replanificaciones (total: ok / sin ruta)",
         col(lambda x: f"{x['replans']} ({x['replans_ok']} / {x['replans_fallidas']})")),
        ("Tiempo de replanificacion (suma)", col(lambda x: ms(x["t_replan"]))),
        ("Tiempo acumulado de busqueda (inicial + replans)", col(lambda x: ms(x["t_busqueda"]))),
        ("Nodos descubiertos (acumulado)", col(lambda x: f"{x['descubiertos']:,}")),
        ("Nodos expandidos (acumulado)", col(lambda x: f"{x['expandidos']:,}")),
        ("Preparacion del mapa por obstaculos", col(lambda x: ms(x["t_preparacion"]))),
        ("Tiempo de animacion (NPC en movimiento)",
         col(lambda x: "simulado" if x["t_animacion"] is None else f"{x['t_animacion']:.1f} s")),
        ("Pasos recorridos / longitud final",
         col(lambda x: f"{x['pasos']} / {x['longitud_final']}")),
    ]


def exportar_informe_csv():
    resumen = CARPETA_DATOS / "informe_obstaculos_dinamicos_resumen.csv"
    detalle = CARPETA_DATOS / "informe_obstaculos_dinamicos_replanificaciones.csv"
    with open(resumen, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metrica", "BFS", "A*"])
        for nombre, vals in filas_informe():
            w.writerow([nombre.strip(), *vals])
        w.writerow(["preparacion matriz estatica (s)", f"{TIEMPO_PREPARACION_ESTATICA:.4f}", ""])
    with open(detalle, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["algoritmo", "origen", "evento", "num", "paso", "posicion", "obstaculo",
                    "resultado", "tiempo_s", "descubiertos", "expandidos",
                    "ruta_restante_anterior", "longitud_nueva"])
        for alg in ("BFS", "A*"):
            ses = resultados_sesion.get(alg)
            for e in (ses["log"] if ses else []):
                w.writerow([alg, ses["origen"], e["evento"], e.get("num", ""), e["paso"],
                            e["posicion"], e["obstaculo"], e["resultado"],
                            f"{e.get('tiempo', 0):.6f}", e.get("descubiertos", ""),
                            e.get("expandidos", ""), e.get("restante_anterior", ""),
                            e.get("longitud_nueva", "")])
    return resumen.name, detalle.name


class VentanaInforme:
    """Ventana secundaria con la tabla comparativa y el registro de replans."""

    def __init__(self):
        self.ventana = pygame.Window("Informe de obstaculos dinamicos - BFS vs A*",
                                     size=(1120, 760))
        self.aviso = ""
        self.ultimo = pygame.time.get_ticks()
        self.negrita = pygame.font.SysFont("Arial", 14, bold=True)
        self.dibujar()

    def _texto(self, sup, txt, pos, color=(230, 230, 230), f=None, ancho=None):
        f = f or fuente
        if ancho:
            while len(txt) > 4 and f.size(txt)[0] > ancho:
                txt = txt[:-4] + "..."
        sup.blit(f.render(txt, True, color), pos)

    def dibujar(self):
        sup = self.ventana.get_surface()
        sup.fill((24, 29, 35))
        self._texto(sup, "Informe de obstaculos dinamicos: BFS vs A*", (20, 12),
                    (255, 255, 255), pygame.font.SysFont("Arial", 20, bold=True))
        y = 48
        for x, titulo in ((20, "Metrica"), (470, "BFS"), (800, "A*")):
            self._texto(sup, titulo, (x, y), (120, 200, 255), self.negrita)
        pygame.draw.line(sup, (90, 100, 110), (20, y + 20), (1100, y + 20))
        y += 26
        for i, (nombre, vals) in enumerate(filas_informe()):
            if i % 2 == 0:
                pygame.draw.rect(sup, (32, 38, 46), (15, y - 2, 1090, 21))
            self._texto(sup, nombre, (20, y), ancho=440)
            self._texto(sup, vals[0], (470, y), ancho=320)
            self._texto(sup, vals[1], (800, y), ancho=300)
            y += 21
        self._texto(sup, f"Preparacion de la matriz estatica (una sola vez al iniciar): "
                    f"{TIEMPO_PREPARACION_ESTATICA:.3f} s", (20, y + 4), (190, 190, 190))
        y += 34
        self._texto(sup, "Registro de replanificaciones (pN = paso del NPC, "
                    "dN = descubiertos, eN = expandidos, L = ruta restante -> nueva)",
                    (20, y), (120, 200, 255), self.negrita)
        y += 24
        for x, alg in ((20, "BFS"), (570, "A*")):
            self._texto(sup, alg, (x, y), (255, 220, 120), self.negrita)
            ses = resultados_sesion.get(alg)
            log = ses["log"][-11:] if ses else []
            for k, e in enumerate(log):
                self._texto(sup, linea_log(e), (x, y + 20 + k * 18), ancho=525)
        self._texto(sup, "S: exportar CSV | ESC: cerrar | Para una comparacion justa use "
                    "'Comparar BFS vs A*'  " + self.aviso, (20, 735), (190, 190, 190))
        self.ventana.flip()

    def refrescar(self):
        if pygame.time.get_ticks() - self.ultimo > 500:
            self.ultimo = pygame.time.get_ticks()
            self.dibujar()

    def evento(self, evento):
        if evento.type == pygame.WINDOWCLOSE or (
                evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE):
            self.ventana.destroy()
            return False
        if evento.type == pygame.KEYDOWN and evento.key == pygame.K_s:
            a, b = exportar_informe_csv()
            self.aviso = f"Guardado: {a}, {b}"
        if evento.type in (pygame.WINDOWEXPOSED, pygame.KEYDOWN):
            self.dibujar()
        return True


informe_ventana = None


def abrir_informe():
    global informe_ventana
    if informe_ventana is None:
        informe_ventana = VentanaInforme()
    else:
        informe_ventana.ventana.focus()
        informe_ventana.dibujar()


# ------------------ botones y panel ------------------

def ciclar(opciones, actual):
    return opciones[(opciones.index(actual) + 1) % len(opciones)]


def etiqueta_boton(nombre):
    return {
        "Obstaculos auto": f"Auto: {'ON' if aparicion_auto else 'OFF'} (P)",
        "Obstaculo ahora": "Obstaculo ahora (O)",
        "Limpiar obstaculos": "Limpiar obstaculos (X)",
        "Comparar BFS vs A*": "Comparar BFS vs A* (C)",
        "Zonas bloqueo": f"Zonas bloqueo: {'ON' if mostrar_zonas_bloqueo else 'OFF'} (B)",
        "Sin ruta": f"Sin ruta: {cfg_sin_ruta}",
        "Tamano": f"Tamano: {cfg_tamano}",
        "Modo": f"Modo: {cfg_modo}",
        "Cada -": "Cada -50", "Cada +": "Cada +50",
        "Max -": "Max -1", "Max +": "Max +1",
        "Detec -": "Deteccion -5", "Detec +": "Deteccion +5",
        "Semilla": f"Semilla: {cfg_semilla} (N)",
        "Informe": "Informe (I)",
    }.get(nombre, nombre)


def boton_habilitado(nombre):
    if nombre in ("Reiniciar", "Visualizar subgrafo", "Informe", "Obstaculos auto",
                  "Zonas bloqueo", "Tamano", "Modo", "Sin ruta", "Cada -", "Cada +",
                  "Max -", "Max +", "Semilla", "Detec -", "Detec +"):
        return True
    if comparando:
        return False
    if nombre == "Animar recorrido":
        return tarea_busqueda is None and ruta_encontrada is not None and not animando
    if nombre == "Obstaculo ahora":
        return (animando and tarea_busqueda is None and not pausa_replan
                and not encuadrando_npc)
    if nombre == "Limpiar obstaculos":
        return (tarea_busqueda is None and not animando
                and bool(gestor_obstaculos.obstaculos))
    return inicio_busqueda is not None and destino_busqueda is not None and tarea_busqueda is None


def accion_cfg(nombre):
    global aparicion_auto, mostrar_zonas_bloqueo, cfg_sin_ruta, cfg_tamano
    global cfg_modo, cfg_cada_pasos, cfg_maximo, cfg_semilla, cfg_radio_deteccion
    if nombre == "Obstaculos auto":
        aparicion_auto = not aparicion_auto
    elif nombre == "Zonas bloqueo":
        mostrar_zonas_bloqueo = not mostrar_zonas_bloqueo
    elif nombre == "Sin ruta":
        cfg_sin_ruta = ciclar(("retirar", "detener"), cfg_sin_ruta)
    elif nombre == "Tamano":
        cfg_tamano = ciclar(TAMANOS, cfg_tamano)
    elif nombre == "Modo":
        cfg_modo = ciclar(MODOS, cfg_modo)
    elif nombre == "Cada -":
        cfg_cada_pasos = max(50, cfg_cada_pasos - 50)
    elif nombre == "Cada +":
        cfg_cada_pasos = min(1000, cfg_cada_pasos + 50)
    elif nombre == "Max -":
        cfg_maximo = max(1, cfg_maximo - 1)
    elif nombre == "Max +":
        cfg_maximo = min(30, cfg_maximo + 1)
    elif nombre == "Detec -":
        cfg_radio_deteccion = max(5, cfg_radio_deteccion - 5)
    elif nombre == "Detec +":
        cfg_radio_deteccion = min(100, cfg_radio_deteccion + 5)
    elif nombre == "Semilla":
        cfg_semilla += 1
        gestor_obstaculos.rng.seed(cfg_semilla)


def limpiar_obstaculos_manual():
    global mensaje
    if boton_habilitado("Limpiar obstaculos"):
        limpiar_mundo_dinamico()
        mensaje = "Obstaculos dinamicos retirados. Mapa limpio."


def pulsar_boton(pos):
    for nombre, rect in botones.items():
        if rect.collidepoint(pos) and boton_habilitado(nombre):
            if nombre == "Ejecutar BFS": ejecutar_busqueda("BFS")
            elif nombre == "Ejecutar A*": ejecutar_busqueda("A*")
            elif nombre == "Animar recorrido": animar_recorrido()
            elif nombre == "Visualizar subgrafo": abrir_subgrafo()
            elif nombre == "Informe": abrir_informe()
            elif nombre == "Obstaculo ahora": generar_obstaculo()
            elif nombre == "Limpiar obstaculos": limpiar_obstaculos_manual()
            elif nombre == "Comparar BFS vs A*": iniciar_comparacion()
            elif nombre == "Reiniciar": reiniciar_busqueda()
            else: accion_cfg(nombre)
            return


def dibujar_panel():
    y = ALTO - PANEL
    pygame.draw.rect(pantalla, (30, 35, 40), (0, y, ANCHO, PANEL))
    for nombre, rect in botones.items():
        habilitado = boton_habilitado(nombre)
        activo = ((nombre == "Obstaculos auto" and aparicion_auto)
                  or (nombre == "Zonas bloqueo" and mostrar_zonas_bloqueo))
        color = (40, 130, 80) if (habilitado and activo) else (
            (48, 95, 125) if habilitado else (55, 58, 60))
        pygame.draw.rect(pantalla, color, rect, border_radius=5)
        texto = fuente.render(etiqueta_boton(nombre), True,
                              (255, 255, 255) if habilitado else (145, 145, 145))
        pantalla.blit(texto, texto.get_rect(center=rect.center))
    movimientos = len(ruta_encontrada) - 1 if ruta_encontrada is not None else "--"
    ses = sesion
    ini = ses["inicial"]
    resumen = (f"{estadisticas.get('algoritmo', '--')} | Estado: {estadisticas.get('estado', 'Sin ejecutar')} | "
               f"Tiempo: {estadisticas.get('tiempo', 0):.4f} s | "
               f"Descubiertos: {estadisticas.get('descubiertos', 0):,} | "
               f"Expandidos: {estadisticas.get('expandidos', 0):,} | Movimientos: {movimientos}")
    vista = "Posiciones validas" if mostrar_posiciones_validas else nombres_vista[modo]
    bloqueadas = cantidad_validas_estatica - cantidad_validas
    textos = [
        mensaje,
        resumen,
        (f"Obstaculos activos: {len(gestor_obstaculos.obstaculos)} | generados: {ses['obstaculos']} | "
         f"sin efecto: {ses['sin_efecto']} | replanificaciones: {ses['replans']} "
         f"(ok {ses['replans_ok']}, sin ruta {ses['replans_fallidas']}) | retirados: {ses['retirados']}"),
        (f"Aparicion: auto {'ON' if aparicion_auto else 'OFF'} cada {cfg_cada_pasos} pasos, max {cfg_maximo} | "
         f"tamano {cfg_tamano} | modo {cfg_modo} | sin ruta: {cfg_sin_ruta} | deteccion {cfg_radio_deteccion} px | semilla {cfg_semilla}"),
        (f"Busqueda acumulada: {ses['t_busqueda']:.4f} s (inicial {0 if ini is None else ini['tiempo']:.4f} s, "
         f"replans {ses['t_replan']:.4f} s) | Prep. mapa: estatica {TIEMPO_PREPARACION_ESTATICA:.3f} s, "
         f"obstaculos {ses['t_preparacion'] * 1000:.2f} ms | Animacion: {ses['t_animacion']:.1f} s | Pasos: {ses['pasos']}"),
        ("Camara siguiendo al NPC (zoom fijo) | Ruta: amarilla | Descartada: naranja | Rastro: rojo" if seguimiento_camara else
         "Clic: inicio/destino | Arrastrar: camara | Rueda: zoom | Ruta: amarilla | Descartada: naranja | Rastro: rojo"),
        "TAB/1-3: vistas | G/4: binaria | V: validas | J: rejilla | H: hitbox | R: centrar | O: obstaculo | P: auto | X: limpiar | B: zonas | N: semilla | C: comparar | I: informe",
        f"Vista: {vista} | NPC: 32x48 | Hitbox: 15x7 | Inicio: {inicio_busqueda} | Destino: {destino_busqueda}",
        (f"Matriz: {ancho_mapa}x{alto_mapa} | Validas (efectiva): {cantidad_validas:,} ({porcentaje_validas:.2f}%) | "
         f"Invalidas: {cantidad_invalidas:,} | Bloqueadas por dinamicos: {bloqueadas:,} | Obstaculos estaticos (px): {cantidad_obstaculos:,}"),
    ]
    for i, texto in enumerate(textos):
        pantalla.blit(fuente.render(texto, True, (225, 230, 235)), (15, y + 114 + i * 18))


inicio_busqueda = destino_busqueda = tarea_busqueda = None
ruta_encontrada = None
estadisticas = {}
animando = False
indice_ruta = 0
acumulado_ruta = 0.0
mensaje = "Selecciona el inicio con un clic y despues el destino."
capa_ruta = pygame.Surface((ancho_mapa,alto_mapa),pygame.SRCALPHA)
capa_ruta.fill((0,0,0,0))
ruta_escalada = None

# --- Estado de obstaculos dinamicos / replanificacion ---
capa_descartada = pygame.Surface((ancho_mapa,alto_mapa),pygame.SRCALPHA)  # tramos reemplazados
capa_descartada.fill((0,0,0,0))
descartada_escalada = None
ruta_inicial = None          # ruta de la busqueda inicial (para repetir la animacion)
ruta_np = None               # ruta vigente como array (N,2) para detectar bloqueos
algoritmo_activo = None
pausa_replan = False         # NPC quieto mientras se replanifica
replan_actual = None
pasos_desde_obstaculo = 0
efectos_aparicion = []
comparando = False
tarea_comparacion = None
mostrar_zonas_bloqueo = False
aparicion_auto = False
cfg_cada_pasos = 150         # un obstaculo cada N pasos del NPC (150 px ~ 1 s)
cfg_maximo = 5               # maximo de obstaculos automaticos por recorrido
cfg_tamano = "Mixto"
cfg_modo = MODO_RUTA
cfg_sin_ruta = "retirar"     # si un obstaculo cierra toda ruta: retirarlo o detener
cfg_semilla = SEMILLA_INICIAL
cfg_radio_deteccion = 25     # el NPC detecta bloqueos a <= N nodos por delante
resultados_sesion = {}       # ultimo resultado de cada algoritmo (informe)
sesion = nueva_sesion(None)

_filas_botones = (
    (ALTO-PANEL+8, 34, ("Ejecutar BFS","Ejecutar A*","Animar recorrido","Reiniciar","Visualizar subgrafo","Informe")),
    (ALTO-PANEL+46, 30, ("Obstaculos auto","Obstaculo ahora","Limpiar obstaculos","Comparar BFS vs A*","Zonas bloqueo","Sin ruta")),
)
botones = {}
for _y, _alto, _nombres in _filas_botones:
    for _i, _n in enumerate(_nombres):
        botones[_n] = pygame.Rect(15+_i*185, _y, 175, _alto)
_y3 = ALTO-PANEL+80
botones["Tamano"] = pygame.Rect(15, _y3, 175, 28)
botones["Modo"] = pygame.Rect(200, _y3, 175, 28)
for _i, _n in enumerate(("Cada -","Cada +","Max -","Max +")):
    botones[_n] = pygame.Rect(385+_i*92, _y3, 87, 28)
botones["Semilla"] = pygame.Rect(753, _y3, 175, 28)
botones["Detec -"] = pygame.Rect(938, _y3, 118, 28)
botones["Detec +"] = pygame.Rect(1062, _y3, 118, 28)
clic_inicial = None
hubo_arrastre = False


# ============================================================
# 14. BUCLE PRINCIPAL
# ============================================================

reloj = pygame.time.Clock()

ejecutando = True
arrastrando = False
posicion_anterior = (0, 0)

while ejecutando:

    # Tiempo transcurrido desde el cuadro anterior.
    dt = min(
        reloj.tick(60) / 1000.0,
        0.05
    )

    for evento in pygame.event.get():

        origen_evento = getattr(evento, "window", None)
        id_ventana = getattr(origen_evento, "id", origen_evento)
        if visualizador_subgrafo is not None and id_ventana == visualizador_subgrafo.ventana.id:
            if not visualizador_subgrafo.evento(evento):
                visualizador_subgrafo = None
            continue  # Sus teclas y clics nunca llegan al mapa principal.
        if informe_ventana is not None and id_ventana == informe_ventana.ventana.id:
            if not informe_ventana.evento(evento):
                informe_ventana = None
            continue
        if id_ventana is not None and id_ventana != ventana_principal.id:
            continue  # Evento pendiente de una ventana secundaria ya cerrada.
        if evento.type == pygame.WINDOWCLOSE:
            ejecutando = False
            continue

        if evento.type == pygame.QUIT:
            ejecutando = False

        # ----------------------------------------------------
        # TECLADO
        # ----------------------------------------------------

        if evento.type == pygame.KEYDOWN:

            if evento.key == pygame.K_ESCAPE:
                ejecutando = False

            elif evento.key == pygame.K_TAB:
                # TAB recorre las tres vistas originales.
                if modo == 3:
                    modo = (modo_anterior_binario + 1) % 3
                else:
                    modo = (modo + 1) % 3
                modo_anterior_binario = modo
                actualizar_vista()

            elif evento.key == pygame.K_1:
                modo = 0
                modo_anterior_binario = modo
                actualizar_vista()

            elif evento.key == pygame.K_2:
                modo = 1
                modo_anterior_binario = modo
                actualizar_vista()

            elif evento.key == pygame.K_3:
                modo = 2
                modo_anterior_binario = modo
                actualizar_vista()

            elif evento.key == pygame.K_4:
                modo_anterior_binario = modo if modo != 3 else modo_anterior_binario
                modo = 3
                actualizar_vista()

            elif evento.key == pygame.K_g:
                # G alterna entre la vista actual y la matriz binaria.
                if modo == 3:
                    modo = modo_anterior_binario
                else:
                    modo_anterior_binario = modo
                    modo = 3
                actualizar_vista()

            elif evento.key == pygame.K_v:
                # V conserva el modo anterior al activar/desactivar la vista.
                mostrar_posiciones_validas = not mostrar_posiciones_validas
                actualizar_vista()

            elif evento.key == pygame.K_j:
                # J activa/desactiva la cuadrícula de referencia.
                mostrar_rejilla = not mostrar_rejilla

            elif evento.key == pygame.K_r and not seguimiento_camara:
                centrar_mapa()

            elif evento.key == pygame.K_h:
                mostrar_hitbox_pies = not mostrar_hitbox_pies

            elif evento.key == pygame.K_o:
                generar_obstaculo()

            elif evento.key == pygame.K_p:
                accion_cfg("Obstaculos auto")

            elif evento.key == pygame.K_x:
                limpiar_obstaculos_manual()

            elif evento.key == pygame.K_b:
                mostrar_zonas_bloqueo = not mostrar_zonas_bloqueo

            elif evento.key == pygame.K_n:
                accion_cfg("Semilla")

            elif evento.key == pygame.K_c and boton_habilitado("Comparar BFS vs A*"):
                iniciar_comparacion()

            elif evento.key == pygame.K_i:
                abrir_informe()

        # ----------------------------------------------------
        # ZOOM CON LA RUEDA DEL RATON
        # ----------------------------------------------------

        if evento.type == pygame.MOUSEWHEEL and not seguimiento_camara:

            mouse_x, mouse_y = pygame.mouse.get_pos()

            zoom_anterior = zoom

            if evento.y > 0:
                zoom = min(
                    zoom * 1.15,
                    zoom_maximo
                )
            else:
                zoom = max(
                    zoom / 1.15,
                    zoom_minimo
                )

            factor = zoom / zoom_anterior

            # Mantener como referencia el punto bajo el ratón.
            desplazamiento_x = (
                mouse_x -
                (mouse_x - desplazamiento_x) * factor
            )

            desplazamiento_y = (
                mouse_y -
                (mouse_y - desplazamiento_y) * factor
            )

            actualizar_vista()

        # ----------------------------------------------------
        # ARRASTRAR EL MAPA CON EL RATON
        # ----------------------------------------------------

        if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
            if evento.pos[1] >= ALTO-PANEL:
                pulsar_boton(evento.pos)
            elif not seguimiento_camara:
                clic_inicial = evento.pos
                posicion_anterior = evento.pos
                hubo_arrastre = False
                arrastrando = True
        if evento.type == pygame.MOUSEMOTION and arrastrando:
            if (abs(evento.pos[0]-clic_inicial[0]) + abs(evento.pos[1]-clic_inicial[1])) > 4:
                hubo_arrastre = True
            if hubo_arrastre:
                desplazamiento_x += evento.pos[0]-posicion_anterior[0]
                desplazamiento_y += evento.pos[1]-posicion_anterior[1]
                posicion_anterior = evento.pos
        if evento.type == pygame.MOUSEBUTTONUP and evento.button == 1:
            if arrastrando and not hubo_arrastre:
                seleccionar_punto(evento.pos)
            arrastrando = False
            clic_inicial = None
        if evento.type == pygame.WINDOWFOCUSLOST:
            arrastrando = False
            clic_inicial = None

    # --------------------------------------------------------
    # ACTUALIZAR EL NPC
    # --------------------------------------------------------

    avanzar_busqueda()
    avanzar_comparacion()
    if not encuadrando_npc:
        actualizar_npc(dt)
    gestionar_deteccion()
    gestionar_aparicion_automatica()
    actualizar_efectos(dt)
    actualizar_seguimiento(dt)
    if informe_ventana is not None:
        informe_ventana.refrescar()

    # ========================================================
    # DIBUJAR EL MAPA
    # ========================================================

    pantalla.fill((20, 23, 27))

    pantalla.blit(
        mapa_escalado,
        (
            int(desplazamiento_x),
            int(desplazamiento_y)
        )
    )

    # Dibujar la cuadrícula si está activada.
    dibujar_cuadricula()

    # El recorrido permanece sobre todas las vistas y debajo del NPC.
    dibujar_resultado()
    dibujar_rastro()

    # Obstaculos dinamicos: los de "atras" van bajo el NPC, los de "adelante" sobre el.
    dibujar_zonas_bloqueo()
    dibujar_obstaculos(False)

    # Dibujar el aventurero encima del mapa y de la cuadrícula.
    dibujar_npc()
    dibujar_obstaculos(True)

    # Dibujar el rectángulo de referencia de los pies.
    dibujar_hitbox_pies()
    dibujar_efectos()

    # ========================================================
    # PANEL INFERIOR
    # ========================================================

    dibujar_panel()

    pygame.display.flip()


# ============================================================
# 15. CERRAR PYGAME
# ============================================================

pygame.quit()