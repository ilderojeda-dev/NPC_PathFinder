import pygame
import numpy as np
from pathlib import Path
from time import perf_counter, time_ns
import math
import csv
import interfaz_pygame as ui
from algoritmos_busqueda import MotorPathfinding, ALGORITMOS_DISPONIBLES

from obstaculos_dinamicos import (
    GestorObstaculosDinamicos, TAMANOS
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
PANEL = 220   # Barra de acciones y tarjetas; el resto es viewport del mapa

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
pygame.display.set_caption("NPC PathFinder | Forest Navigation")

fuente = ui.font(14)

if not RUTA_IMAGEN.exists():
    raise FileNotFoundError(
        f"No se encontro la imagen del mapa: {RUTA_IMAGEN.name}"
    )

imagen_original = pygame.image.load(
    str(RUTA_IMAGEN)
).convert()

ancho_mapa = imagen_original.get_width()
alto_mapa = imagen_original.get_height()


# ============================================================
# 3. CREAR LA MATRIZ BINARIA DE TRANSITABILIDAD
# ============================================================

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
# La efectiva es consultada por las busquedas, colisiones, clics y el
# visualizador de subgrafos la consultan sin cambios.
matriz_posiciones_validas = gestor_obstaculos.efectiva
motor_pathfinding = MotorPathfinding(matriz_posiciones_validas_estatica, matriz_posiciones_validas)
preparacion_alt = motor_pathfinding.preparar_alt()
# Alias: la implementacion unica de los tres algoritmos vive en el modulo.
buscar_ruta = motor_pathfinding.buscar_ruta
cantidad_validas = int(np.count_nonzero(matriz_posiciones_validas))
cantidad_validas_estatica = cantidad_validas
cantidad_invalidas = int(matriz_posiciones_validas.size) - cantidad_validas
porcentaje_validas = 100 * cantidad_validas / matriz_posiciones_validas.size
colores_posiciones = np.empty((*matriz_posiciones_validas.shape,3), dtype=np.uint8)
colores_posiciones[:] = (220,55,55)
colores_posiciones[matriz_posiciones_validas == 1] = (35,190,85)
imagen_posiciones_validas = pygame.surfarray.make_surface(colores_posiciones.transpose(1,0,2))


cantidad_transitable = int(np.count_nonzero(matriz_transitabilidad == 1))
cantidad_obstaculos = int(np.count_nonzero(matriz_transitabilidad == 0))
total_celdas = int(matriz_transitabilidad.size)

porcentaje_transitable = cantidad_transitable * 100 / total_celdas

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

# ============================================================
# 4. CARGAR Y DIVIDIR EL SPRITE DEL AVENTURERO
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
# 5. CONFIGURAR LA VISUALIZACION DEL MAPA
# ============================================================

# Modos de vista:
# 0 = Imagen original.
# 3 = Matriz binaria de transitabilidad (G o 4 activan/desactivan este modo).

modo = 0
modo_anterior_binario = 0
mostrar_posiciones_validas = False

nombres_vista = {
    0: "Imagen original",
    3: "Matriz binaria de transitabilidad"
}

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
# 6. CONFIGURAR LA POSICION Y ANIMACION DEL NPC
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
# 7. ACTUALIZAR LA VISTA DEL MAPA
# ============================================================

def actualizar_vista():
    global mapa_escalado

    if mostrar_posiciones_validas:
        superficie = imagen_posiciones_validas
    elif modo == 3:
        superficie = imagen_transitabilidad
    else:
        superficie = imagen_original

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
# 8. ACTUALIZAR EL MOVIMIENTO DEL NPC
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
    actualizar_reloj_recorrido()
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
                cerrar_recorrido("Interrumpido: paso no valido")
                break
            mover_npc_con_colisiones(dx, dy, 1)
            if centro_hitbox() != (nx, ny):
                animando = False
                mensaje = "Recorrido detenido por colision."
                cerrar_recorrido("Interrumpido: colision")
                break
            direccion_npc = ("derecha" if dx > 0 else "izquierda" if dx < 0
                             else "abajo" if dy > 0 else "arriba")
            indice_ruta += 1
            acumulado_ruta -= 1
            sesion["pasos"] += 1
            sesion["rutas"][-1]["realizados"] += 1
            pasos_desde_obstaculo += 1
        if indice_ruta == len(ruta_encontrada) - 1:
            animando = False
            mensaje = "Destino alcanzado."
            cerrar_recorrido("Destino alcanzado")
            sesion["rutas"][-1]["completada"] = True
            sesion["longitud_final"] = sesion["pasos"]
        actualizar_reloj_recorrido()
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
# 9. DIBUJAR EL NPC Y EL RECTANGULO DE SUS PIES
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


# Preparacion compartida de landmarks, ejecutada por lotes.
def avanzar_preparacion_alt():
    global preparacion_alt, mensaje
    if preparacion_alt is None:
        return
    try:
        progreso = next(preparacion_alt)
        mensaje = (f"Preparando mapa ALT: landmark {progreso['landmark']}/{progreso['cantidad']} "
                   f"- {progreso['expandidos']:,} posiciones")
    except StopIteration:
        preparacion_alt = None
        mensaje = "Mapa preparado. Selecciona inicio y destino, o ejecuta la busqueda."


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
    interrumpir_recorrido("Interrumpido por reinicio")
    detener_seguimiento()
    global inicio_busqueda, destino_busqueda, tarea_busqueda, ruta_encontrada
    global animando, mensaje, estadisticas, rastro_modificado, ruta_escalada
    global moviendo_npc, comparando, tarea_comparacion, pausa_replan
    global replan_actual, sesion, algoritmo_activo, ruta_inicial, ruta_np
    global pasos_desde_obstaculo
    if tarea_busqueda is not None:
        tarea_busqueda.close()
        sesion["resultado"] = "Busqueda cancelada"
    if tarea_comparacion is not None:
        tarea_comparacion.close()
        contexto_comparacion["estado"] = "Cancelada"
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
        mensaje = "Puntos listos. Selecciona un algoritmo y ejecuta la busqueda."
    else:
        mensaje = "Pulsa Reiniciar para seleccionar otros puntos."


def ejecutar_busqueda(algoritmo):
    global tarea_busqueda, animando, ruta_encontrada, estadisticas, mensaje, ruta_escalada
    global algoritmo_activo, sesion, ruta_inicial, ruta_np, pausa_replan, replan_actual
    if preparacion_alt is not None or inicio_busqueda is None or destino_busqueda is None or tarea_busqueda is not None or comparando:
        return
    interrumpir_recorrido("Interrumpido por nueva busqueda")
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
    tarea_busqueda = buscar_ruta(inicio_busqueda, destino_busqueda, algoritmo)
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
            registrar_inicial(sesion, estadisticas, None)
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
        sesion["reloj_inicio"] = sesion["reloj_ultimo"] = perf_counter()
        sesion["resultado"] = "En recorrido"
        if not animando:
            sesion["rutas"][-1]["completada"] = True
            cerrar_recorrido("Destino alcanzado")
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
    """Ventana secundaria. Cerrar esta ventana no llama a interrumpir_recorrido("Interrumpido al cerrar")
pygame.quit()."""
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
        superficie.fill(ui.BG)
        if self.imagen is None:
            textos = [("Region en coordenadas del mapa (x = columna, y = fila)",(20,20)),
                      ("Clic o TAB: campo | Escribir: valor | ENTER: visualizar | ESC: cerrar",(20,360)),
                      (self.error,(20,390))]
            for i,nombre in enumerate(("X inicial", "Y inicial", "Ancho", "Alto")):
                superficie.blit(fuente.render(nombre,True,ui.TEXT),(130,75+i*55))
                rect = self.rects[i]
                pygame.draw.rect(superficie,ui.CARD,rect)
                pygame.draw.rect(superficie,ui.ACCENT if i==self.activo else ui.BORDER,rect,2)
                superficie.blit(fuente.render(self.campos[i],True,(255,255,255)),(rect.x+10,rect.y+9))
            pygame.draw.rect(superficie,(55,88,64),self.confirmar,border_radius=4)
            superficie.blit(fuente.render("Visualizar",True,(255,255,255)),(320,310))
        else:
            x,y,w,h = self.region
            pygame.draw.rect(superficie,(55,88,64),self.volver,border_radius=4)
            superficie.blit(fuente.render("Cambiar region",True,(255,255,255)),(30,23))
            textos = [(f"Origen: ({x}, {y}) | Region: {w} x {h} | Nodos: {self.nodos:,} | Aristas: {self.aristas:,}",(15,60)),
                      ("Azul: nodos validos | Rojo: conexiones internas | Fondo: mapa original",(15,82)),
                      ("Coordenadas: X crece a la derecha; Y hacia abajo. ESC cierra solo esta ventana.",(15,815))]
            superficie.blit(self.presentacion,((960-self.presentacion.get_width())//2,105))
        for texto,pos in textos:
            superficie.blit(fuente.render(texto,True,ui.TEXT),pos)
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
# 10. OBSTACULOS DINAMICOS, REPLANIFICACION, COMPARACION E INFORME
# ============================================================
# Flujo en vivo: aparece un obstaculo -> se actualiza la matriz efectiva solo
# en su ventana -> se comprueba (vectorizado) si bloquea el tramo pendiente de
# la ruta -> si lo bloquea, se pausa el NPC y se vuelve a ejecutar el mismo
# algoritmo desde la posicion actual hacia el destino original.

DURACION_EFECTO = 0.8    # Segundos del destello de aparicion.


def nueva_sesion(algoritmo, origen="Animacion en vivo"):
    ses = dict(id=len(historial_sesiones)+1, inicio=inicio_busqueda, destino=destino_busqueda,
                rutas=[], tipos={"roca": 0, "arbusto": 0, "tronco": 0},
                reloj_inicio=None, reloj_ultimo=None, reloj_fin=None,
                t_total=0.0, t_movimiento=0.0, t_detenido=0.0,
                algoritmo=algoritmo, origen=origen, semilla=cfg_semilla,
                inicial=None, obstaculos=0, sin_efecto=0, omitidos=0,
                retirados=0, replans=0, replans_ok=0, replans_fallidas=0,
                t_busqueda=0.0, t_replan=0.0, descubiertos=0, expandidos=0,
                t_preparacion=0.0, t_animacion=0.0, pasos=0,
                longitud_final=None, resultado="--", log=[])
    if algoritmo is not None:
        historial_sesiones.append(ses)
    return ses


def registrar_ruta(ses, longitud, tiempo_busqueda):
    # El NPC ya ocupa el primer nodo de cada ruta cuando se registra.
    ses["rutas"].append(dict(longitud=longitud, nodos_totales=longitud + 1,
                             realizados=0, completada=False,
                             tiempo_busqueda=tiempo_busqueda))


def nodos_recorridos_ruta(ruta):
    return ruta["realizados"] + 1


def actualizar_reloj_recorrido():
    if sesion["reloj_inicio"] is None or sesion["reloj_fin"] is not None:
        return
    ahora = perf_counter()
    intervalo = max(0.0, ahora - sesion["reloj_ultimo"])
    sesion["reloj_ultimo"] = ahora
    clave = "t_movimiento" if moviendo_npc and not pausa_replan and not encuadrando_npc else "t_detenido"
    sesion[clave] += intervalo
    sesion["t_total"] = ahora - sesion["reloj_inicio"]


def cerrar_recorrido(resultado):
    actualizar_reloj_recorrido()
    if sesion["reloj_inicio"] is not None and sesion["reloj_fin"] is None:
        sesion["reloj_fin"] = sesion["reloj_ultimo"]
    sesion["resultado"] = resultado


def interrumpir_recorrido(motivo):
    if sesion["reloj_inicio"] is not None and sesion["reloj_fin"] is None:
        cerrar_recorrido(motivo)


def registrar_inicial(ses, res, longitud):
    ses["inicial"] = dict(tiempo=res["tiempo"], descubiertos=res["descubiertos"],
                          expandidos=res["expandidos"], longitud=longitud)
    ses["t_busqueda"] = res["tiempo"]
    ses["descubiertos"] = res["descubiertos"]
    ses["expandidos"] = res["expandidos"]
    ses["longitud_final"] = longitud
    ses["resultado"] = res.get("estado", "Ruta encontrada")
    if longitud is not None:
        registrar_ruta(ses, longitud, res["tiempo"])


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
    if sesion["reloj_inicio"] is not None:
        nueva = nueva_sesion(algoritmo_activo)
        if ini:
            registrar_inicial(nueva, dict(ini, estado="Ruta encontrada"), ini["longitud"])
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
        cfg_tamano, ruta_encontrada, indice_ruta, npc,
        destino_busqueda, rango=(cfg_radio_deteccion + 25, cfg_radio_deteccion + 55))
    if obs is None:
        mensaje = "No hay un lugar valido para un obstaculo en este momento."
        return False
    obs.paso = sesion["pasos"]
    info = gestor_obstaculos.colocar(obs)
    registrar_cambio_mapa(info)
    efectos_aparicion.append(dict(obs=obs, t=0.0))
    sesion["obstaculos"] += 1
    sesion["tipos"][obs.tipo] += 1
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
    actualizar_reloj_recorrido()
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
    actualizar_reloj_recorrido()
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
        registrar_ruta(sesion, len(ruta) - 1, resultado["tiempo"])
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
        cerrar_recorrido("Sin ruta posible: recorrido detenido")
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


# ------------------ comparacion de los tres algoritmos ------------------

def _buscar_progreso(inicio, objetivo, alg, texto):
    gen = buscar_ruta(inicio, objetivo, alg, LOTE_EXPANSIONES)
    while True:
        try:
            p = next(gen)
        except StopIteration as fin:
            return fin.value
        yield f"{texto} - {p['expandidos']:,} nodos expandidos"


def generador_comparacion(inicio, destino):
    for alg in ALGORITMOS_DISPONIBLES:
        res = yield from _buscar_progreso(inicio, destino, alg, f"Comparando {alg}")
        ruta = res["ruta"]
        resultados_comparacion.append(dict(
            algoritmo=alg, tiempo=res["tiempo"], expandidos=res["expandidos"],
            nodos_ruta=None if ruta is None else len(ruta), estado=res["estado"],
            criterio_nodos=res.get("criterio_nodos", "Descubiertos unicos / expandidos hacia el destino"),
            preparacion_alt_s=motor_pathfinding.alt.tiempo if "ALT" in alg else 0.0))
    return "Comparacion estatica terminada. Sin obstaculos dinamicos ni animacion."


def iniciar_comparacion():
    global comparando, tarea_comparacion, animando, ruta_encontrada
    global ruta_escalada, mensaje, pausa_replan, replan_actual, contexto_comparacion, numero_comparacion, resultados_comparacion
    if preparacion_alt is not None or inicio_busqueda is None or destino_busqueda is None or comparando or tarea_busqueda is not None:
        return
    interrumpir_recorrido("Interrumpido por comparacion")
    animando = pausa_replan = False
    replan_actual = None
    limpiar_mundo_dinamico()
    ubicar_en_inicio()
    ruta_encontrada = None
    capa_ruta.fill((0, 0, 0, 0))
    ruta_escalada = None
    resultados_comparacion = []  # Cada comparacion conserva su propia lista.
    numero_comparacion += 1
    contexto_comparacion = dict(id=numero_comparacion, inicio=inicio_busqueda, destino=destino_busqueda,
                                estado="En curso", resultados=resultados_comparacion,
                                preparacion_alt_s=motor_pathfinding.alt.tiempo)
    historial_comparaciones.append(contexto_comparacion)
    if informe_ventana is not None:
        informe_ventana.indice_comparacion = len(historial_comparaciones) - 1
        informe_ventana.comparacion = True
        informe_ventana.aviso = ""
    comparando = True
    tarea_comparacion = generador_comparacion(inicio_busqueda, destino_busqueda)
    mensaje = "Comparando busquedas sobre el mismo mapa estatico..."


def avanzar_comparacion():
    global comparando, tarea_comparacion, mensaje
    if tarea_comparacion is None:
        return
    try:
        mensaje = next(tarea_comparacion)
    except StopIteration as fin:
        tarea_comparacion, comparando = None, False
        contexto_comparacion["estado"] = "Terminada"
        mensaje = fin.value
        abrir_informe(comparacion=True)




def ms(t):
    return "--" if t is None else f"{t * 1000:.1f} ms"


def filas_informe(ses):
    if ses is None:
        return [("Sin ejecuciones individuales", "")]
    ini = ses["inicial"]
    valor = lambda clave: "--" if ini is None else ini[clave]
    filas = [
        ("Ejecucion", str(ses["id"])), ("Algoritmo", ses["algoritmo"]),
        ("Inicio / destino", f"{ses['inicio']} / {ses['destino']}"),
        ("A. Busqueda inicial", ""),
        ("Tiempo de busqueda inicial (s)", valor("tiempo")),
        ("Nodos descubiertos", valor("descubiertos")),
        ("Nodos expandidos", valor("expandidos")),
        ("Longitud inicial (movimientos)", valor("longitud")),
        ("B. Obstaculos dinamicos", ""),
        ("Total generados", ses["obstaculos"]),
        ("Rocas", ses["tipos"]["roca"]),
        ("Arboles (arbustos del catalogo)", ses["tipos"]["arbusto"]),
        ("Palos (troncos del catalogo)", ses["tipos"]["tronco"]),
        ("C. Historial de rutas", ""),
    ]
    if "ALT" in ses["algoritmo"]:
        filas.insert(8, ("Preparacion ALT compartida (s, fuera de busqueda)", motor_pathfinding.alt.tiempo))
    filas.append(("Ruta", ("Nodos recorridos / nodos totales", "Tiempo de busqueda")))
    for i, ruta in enumerate(ses["rutas"]):
        nombre = "Ruta inicial" if i == 0 else f"Ruta {i + 1}"
        filas.append((nombre, (f"{nodos_recorridos_ruta(ruta)} / {ruta['nodos_totales']}",
                               ruta['tiempo_busqueda'])))
    filas += [
        ("Cantidad total de rutas creadas", len(ses["rutas"])),
        ("D. Recorrido completo", ""),
        ("Tiempo total de recorrido (s, incluye pausas)", ses["t_total"]),
        ("Tiempo en movimiento (s)", ses["t_movimiento"]),
        ("Tiempo detenido (s)", ses["t_detenido"]),
        ("Pasos recorridos", ses["pasos"]),
        ("Resultado final / estado actual", ses["resultado"]),
    ]
    return filas


def exportar_informe_csv(ses=None, comparacion=False, registro_comparacion=None):
    if comparacion:
        registro = registro_comparacion if registro_comparacion is not None else contexto_comparacion
        if not registro:
            return "No hay una comparacion seleccionada"
        ruta = CARPETA_DATOS / f"comparacion_busquedas_{IDENTIFICADOR_APERTURA}_{registro['id']}.csv"
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["algoritmo", "tiempo_busqueda_s", "nodos_explorados",
                        "nodos_ruta", "estado", "inicio", "destino", "criterio_nodos", "preparacion_alt_s"])
            for r in registro['resultados']:
                w.writerow([r["algoritmo"], r["tiempo"], r["expandidos"],
                            r["nodos_ruta"], r["estado"], registro['inicio'], registro['destino'],
                            r["criterio_nodos"], r["preparacion_alt_s"]])
        return ruta.name
    if ses is None:
        return "No hay una ejecucion seleccionada"
    ruta = CARPETA_DATOS / f"informe_individual_{IDENTIFICADOR_APERTURA}_{ses['id']}_{ses['algoritmo'].replace('*', 'star')}.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metrica", "valor", "tiempo_busqueda_s"])
        for nombre, valor in filas_informe(ses):
            if isinstance(valor, tuple):
                nodos, tiempo = valor
                w.writerow([nombre, nodos, f"{tiempo:.6f}" if isinstance(tiempo, float) else tiempo])
            else:
                w.writerow([nombre, valor, ""])
    return ruta.name


class VentanaInforme:
    """Informe individual seleccionable o comparacion estatica independiente."""
    def __init__(self, comparacion=False):
        self.ventana = pygame.Window("Informes NPC PathFinder", size=(1120, 760))
        self.comparacion = comparacion
        self.indice = max(0, len(historial_sesiones) - 1)
        self.indice_comparacion = max(0, len(historial_comparaciones) - 1)
        self.scroll = 0
        self.aviso = ""
        self.ultimo = pygame.time.get_ticks()
        self.dibujar()

    def comparacion_seleccionada(self):
        return historial_comparaciones[self.indice_comparacion] if historial_comparaciones else None

    def navegacion_habilitada(self, direccion):
        historial = historial_comparaciones if self.comparacion else historial_sesiones
        indice = self.indice_comparacion if self.comparacion else self.indice
        return bool(historial) and 0 <= indice + direccion < len(historial)

    def navegar(self, direccion):
        if not self.navegacion_habilitada(direccion):
            return
        if self.comparacion:
            self.indice_comparacion += direccion
        else:
            self.indice += direccion
            self.scroll = 0
        self.aviso = ""

    def dibujar(self):
        sup=self.ventana.get_surface();sup.fill(ui.BG)
        ui.text(sup,"Resultados",(26,18),size=27,bold=True)
        ui.text(sup,"NPC PATHFINDER / ANALISIS",(26,55),ui.MUTED,11,True)
        self.acciones_ui = {pygame.K_i: pygame.Rect(435,24,150,36),
                            pygame.K_c: pygame.Rect(595,24,150,36),
                            pygame.K_s: pygame.Rect(755,24,140,36),
                            pygame.K_LEFT: pygame.Rect(915,24,80,36),
                            pygame.K_RIGHT: pygame.Rect(1005,24,80,36)}
        for key,rect in self.acciones_ui.items():
            label={pygame.K_i:"Individual",pygame.K_c:"Comparacion",pygame.K_s:"Exportar CSV",
                   pygame.K_LEFT:"Anterior",pygame.K_RIGHT:"Siguiente"}[key]
            habilitado = (self.navegacion_habilitada(-1) if key == pygame.K_LEFT else
                          self.navegacion_habilitada(1) if key == pygame.K_RIGHT else True)
            ui.button(sup,rect,label,enabled=habilitado,primary=key==pygame.K_s,
                      active=(key==pygame.K_c and self.comparacion) or (key==pygame.K_i and not self.comparacion))
        if self.comparacion:
            registro = self.comparacion_seleccionada() or {}
            ui.text(sup,f"COMPARACION {registro.get('id', '--')}  /  {registro.get('estado','Sin ejecutar')}",(26,100),ui.ACCENT,13,True)
            ui.text(sup,f"Inicio {registro.get('inicio')}   -   Destino {registro.get('destino')}",(26,129),ui.MUTED)
            xs=(42,280,540,800)
            ui.box(sup,pygame.Rect(26,175,1060,44))
            for x,t in zip(xs,("ALGORITMO","TIEMPO DE BUSQUEDA","NODOS EXPLORADOS","NODOS DE LA RUTA")):
                ui.text(sup,t,(x,190),ui.MUTED,12,True)
            for i,r in enumerate(registro.get("resultados", [])):
                y=231+i*68
                ui.box(sup,pygame.Rect(26,y,1060,58))
                for x,v in zip(xs,(r['algoritmo'],f"{r['tiempo']:.6f} s",f"{r['expandidos']:,}",
                                   "Sin ruta" if r['nodos_ruta'] is None else f"{r['nodos_ruta']:,}")):
                    ui.text(sup,v,(x,y+17),size=18,bold=True)
            ui.text(sup,"Explorados = expansiones. En BFS Bidireccional se suman ambos extremos.",(26,610),ui.MUTED,13)
            ui.text(sup,f"ALT: preparacion compartida {registro.get('preparacion_alt_s', 0):.3f} s, excluida de las busquedas.",(26,637),ui.MUTED,13)
        else:
            ses=historial_sesiones[self.indice] if historial_sesiones else None
            filas=filas_informe(ses)
            self.scroll=min(self.scroll,max(0,len(filas)-23))
            for i,(nombre,valor) in enumerate(filas[self.scroll:self.scroll+23]):
                y=91+i*25
                section=nombre[:2] in ('A.','B.','C.','D.')
                if section:
                    pygame.draw.rect(sup,ui.CARD,(26,y-2,1060,24),border_radius=5)
                elif i%2==0:
                    pygame.draw.rect(sup,(18,30,27),(26,y-2,1060,24),border_radius=3)
                ui.text(sup,nombre,(38,y),ui.ACCENT if section else ui.MUTED,14,section)
                if isinstance(valor, tuple):
                    nodos, tiempo = valor
                    ui.text(sup,nodos,(540,y),ui.TEXT,13,True,width=300)
                    ui.text(sup,f"{tiempo:.6f} s" if isinstance(tiempo,float) else tiempo,
                            (865,y),ui.TEXT,13,True,width=215)
                else:
                    ui.text(sup,f"{valor:.6f}" if isinstance(valor,float) else valor,(610,y),size=14,bold=True,width=460)
            ui.text(sup,"Rueda para ver todas las rutas. Anterior / Siguiente cambia de ejecucion.",(26,690),ui.MUTED,13)
        self.iniciar_comparacion_rect = pygame.Rect(866,679,220,38)
        if self.comparacion:
            ui.button(sup,self.iniciar_comparacion_rect,"Iniciar comparacion",
                      enabled=boton_habilitado("Comparar busquedas"),primary=True)
        ui.text(sup,self.aviso or "S: exportar   /   ESC: cerrar esta ventana",(26,729),ui.MUTED,13,width=1060)
        self.ventana.flip()

    def refrescar(self):
        if pygame.time.get_ticks() - self.ultimo > 500:
            self.ultimo = pygame.time.get_ticks()
            self.dibujar()

    def evento(self, evento):
        if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
            if self.comparacion and self.iniciar_comparacion_rect.collidepoint(evento.pos):
                if boton_habilitado("Comparar busquedas"):
                    iniciar_comparacion()
                    self.comparacion = True
                    self.aviso = ""
                self.dibujar()
                return True
            for key, rect in getattr(self, "acciones_ui", {}).items():
                if rect.collidepoint(evento.pos):
                    evento = pygame.event.Event(pygame.KEYDOWN, key=key)
                    break
        if evento.type == pygame.WINDOWCLOSE or (evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE):
            self.ventana.destroy()
            return False
        if evento.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - evento.y * 3)
        if evento.type == pygame.KEYDOWN:
            if evento.key == pygame.K_c:
                self.comparacion = True
            elif evento.key == pygame.K_i:
                self.comparacion = False
            elif evento.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self.navegar(1 if evento.key == pygame.K_RIGHT else -1)
            elif evento.key == pygame.K_s:
                actualizar_reloj_recorrido()
                ses = historial_sesiones[self.indice] if historial_sesiones else None
                self.aviso = exportar_informe_csv(ses, self.comparacion, self.comparacion_seleccionada())
        self.dibujar()
        return True


informe_ventana = None


def abrir_informe(comparacion=False):
    global informe_ventana
    if informe_ventana is None:
        informe_ventana = VentanaInforme(comparacion)
    else:
        informe_ventana.comparacion = comparacion
        informe_ventana.scroll = 0
        informe_ventana.ventana.focus()
        informe_ventana.dibujar()




def ciclar(opciones, actual):
    return opciones[(opciones.index(actual) + 1) % len(opciones)]


def etiqueta_boton(nombre):
    return {
        "Obstaculos auto": f"Auto: {'ON' if aparicion_auto else 'OFF'} (P)",
        "Obstaculo ahora": "Obstaculo ahora (Q)",
        "Limpiar obstaculos": "Limpiar obstaculos (X)",
        "Comparar busquedas": "Comparar busquedas (C)",
        "Zonas bloqueo": f"Zonas bloqueo: {'ON' if mostrar_zonas_bloqueo else 'OFF'} (B)",
        "Sin ruta": f"Sin ruta: {cfg_sin_ruta}",
        "Tamano": f"Tamano: {cfg_tamano}",
        "Cada -": "Cada -50", "Cada +": "Cada +50",
        "Max -": "Max -1", "Max +": "Max +1",
        "Detec -": "Deteccion -5", "Detec +": "Deteccion +5",
        "Semilla": f"Semilla: {cfg_semilla} (N)",
        "Informe": "Informe (I)",
    }.get(nombre, nombre)


def boton_habilitado(nombre):
    if nombre in ("Reiniciar", "Visualizar subgrafo", "Informe", "Obstaculos auto",
                  "Zonas bloqueo", "Tamano", "Sin ruta", "Cada -", "Cada +",
                  "Max -", "Max +", "Semilla", "Detec -", "Detec +"):
        return True
    if comparando or preparacion_alt is not None:
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
    global cfg_cada_pasos, cfg_maximo, cfg_semilla, cfg_radio_deteccion
    if nombre == "Obstaculos auto":
        aparicion_auto = not aparicion_auto
    elif nombre == "Zonas bloqueo":
        mostrar_zonas_bloqueo = not mostrar_zonas_bloqueo
    elif nombre == "Sin ruta":
        cfg_sin_ruta = ciclar(("retirar", "detener"), cfg_sin_ruta)
    elif nombre == "Tamano":
        cfg_tamano = ciclar(TAMANOS, cfg_tamano)
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


def accion_interfaz(nombre):
    global algoritmo_seleccionado
    if nombre == "Algoritmo":
        algoritmo_seleccionado = ciclar(ALGORITMOS_DISPONIBLES, algoritmo_seleccionado)
    elif nombre == "Ejecutar busqueda": ejecutar_busqueda(algoritmo_seleccionado)
    elif nombre == "Animar recorrido": animar_recorrido()
    elif nombre == "Visualizar subgrafo": abrir_subgrafo()
    elif nombre == "Informe": abrir_informe()
    elif nombre == "Configuracion": abrir_configuracion()
    elif nombre == "Obstaculo ahora": generar_obstaculo()
    elif nombre == "Limpiar obstaculos": limpiar_obstaculos_manual()
    elif nombre == "Comparar busquedas": iniciar_comparacion()
    elif nombre == "Reiniciar": reiniciar_busqueda()
    else: accion_cfg(nombre)


def habilitado_interfaz(nombre):
    if nombre == "Configuracion": return True
    if nombre == "Algoritmo": return not (comparando or animando or tarea_busqueda is not None)
    if nombre == "Ejecutar busqueda": return boton_habilitado("Ejecutar " + algoritmo_seleccionado)
    return boton_habilitado(nombre)


def cambiar_configuracion(nombre, valor):
    limites = {"cfg_cada_pasos": (50,1000), "cfg_maximo": (1,30), "cfg_radio_deteccion": (5,100)}
    if nombre in limites:
        lo, hi = limites[nombre]
        globals()[nombre] = max(lo,min(hi,int(valor)))
    elif nombre == "cfg_semilla":
        globals()[nombre] = int(valor)
        gestor_obstaculos.rng.seed(int(valor))


def abrir_configuracion():
    global configuracion_ventana
    if configuracion_ventana is None:
        configuracion_ventana = ui.Configuracion(lambda: globals(), accion_interfaz,
                                                  boton_habilitado, cambiar_configuracion)
    else:
        configuracion_ventana.ventana.focus()
        configuracion_ventana.dibujar()


def pulsar_boton(pos):
    for nombre, rect in botones.items():
        if rect.collidepoint(pos) and habilitado_interfaz(nombre):
            accion_interfaz(nombre)
            return


def dibujar_panel():
    y = ALTO - PANEL
    pygame.draw.rect(pantalla,ui.PANEL,(0,y,ANCHO,PANEL))
    pygame.draw.line(pantalla,ui.BORDER,(0,y),(ANCHO,y),1)
    ui.text(pantalla,"NPC / PATHFINDER",(22,y+12),ui.ACCENT,16,True)
    estado = ("Preparando mapa" if preparacion_alt is not None else "Comparando" if comparando else "Replanificando" if pausa_replan else
              "En recorrido" if animando else estadisticas.get("estado","Selecciona inicio y destino"))
    ui.text(pantalla,estado,(ANCHO-365,y+13),ui.MUTED,14,width=340)
    mouse=pygame.mouse.get_pos()
    for nombre,rect in botones.items():
        label = algoritmo_seleccionado + "  >" if nombre=="Algoritmo" else nombre
        if nombre == "Configuracion":
            ui.boton_configuracion(pantalla,rect,hover=rect.collidepoint(mouse))
        else:
            ui.button(pantalla,rect,label,habilitado_interfaz(nombre),
                      primary=nombre=="Ejecutar busqueda",hover=rect.collidepoint(mouse))
    ui.text(pantalla,"BUSQUEDA  /  " + algoritmo_seleccionado,(22,y+105),ui.MUTED,11,True)
    ui.text(pantalla,"NAVEGACION" + ("  /  " + sesion["algoritmo"] if sesion["algoritmo"] else ""),(610,y+105),ui.MUTED,11,True)
    ini=sesion.get("inicial")
    # El reloj del recorrido ya incluye las pausas de replanificacion.
    # Solo se suma la busqueda inicial, previa a pulsar Animar recorrido.
    tiempo_inicial = ini["tiempo"] if ini is not None else estadisticas.get("tiempo", 0.0)
    tiempo_total = tiempo_inicial + sesion["t_total"]
    valores=[("Tiempo de busqueda",f"{estadisticas.get('tiempo',0):.4f} s"),
             ("Nodos explorados",f"{estadisticas.get('expandidos',0):,}"),
             ("Ruta inicial / movimientos","--" if ini is None or ini['longitud'] is None else f"{ini['longitud']:,}"),
             ("Movimientos realizados",f"{sesion['pasos']:,}"),
             ("Rutas creadas",len(sesion['rutas'])),("Tiempo total",f"{tiempo_total:.2f} s")]
    if estadisticas.get('algoritmo') != algoritmo_seleccionado:
        valores[:3]=[(label,"--") for label,_ in valores[:3]]
    if comparando:
        valores=[(label,"--") for label,_ in valores]
    for i,(label,value) in enumerate(valores):
        x=22+i*194+(6 if i>=3 else 0)
        ui.box(pantalla,pygame.Rect(x,y+124,182,74))
        ui.text(pantalla,label,(x+12,y+134),ui.MUTED,11)
        ui.text(pantalla,value,(x+12,y+153),ui.TEXT,24,True)




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
cfg_sin_ruta = "retirar"     # si un obstaculo cierra toda ruta: retirarlo o detener
cfg_semilla = SEMILLA_INICIAL
cfg_radio_deteccion = 10     # el NPC detecta bloqueos a <= N nodos por delante
IDENTIFICADOR_APERTURA = str(time_ns())
resultados_sesion = {}
historial_sesiones = []
historial_comparaciones = []
resultados_comparacion = []
contexto_comparacion = {}
numero_comparacion = 0
sesion = nueva_sesion(None)

algoritmo_seleccionado = ALGORITMOS_DISPONIBLES[0]
configuracion_ventana = None
botones = {}
_x = 22
for _nombre,_ancho in (("Algoritmo",150),("Ejecutar busqueda",160),("Animar recorrido",156),
                      ("Reiniciar",100),("Visualizar subgrafo",164),("Informe",98),("Configuracion",44)):
    botones[_nombre]=pygame.Rect(_x,ALTO-PANEL+47,_ancho,42)
    _x += _ancho+10


clic_inicial = None
hubo_arrastre = False


# ============================================================
# 11. BUCLE PRINCIPAL
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

    actualizar_reloj_recorrido()

    for evento in pygame.event.get():

        origen_evento = getattr(evento, "window", None)
        id_ventana = getattr(origen_evento, "id", origen_evento)
        if configuracion_ventana is not None and id_ventana == configuracion_ventana.ventana.id:
            if not configuracion_ventana.evento(evento):
                configuracion_ventana = None
            continue
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

            elif evento.key == pygame.K_1:
                modo = 0
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

            elif evento.key == pygame.K_r and not seguimiento_camara:
                centrar_mapa()

            elif evento.key == pygame.K_h:
                mostrar_hitbox_pies = not mostrar_hitbox_pies

            elif evento.key == pygame.K_q:
                generar_obstaculo()

            elif evento.key == pygame.K_p:
                accion_cfg("Obstaculos auto")

            elif evento.key == pygame.K_x:
                limpiar_obstaculos_manual()

            elif evento.key == pygame.K_b:
                mostrar_zonas_bloqueo = not mostrar_zonas_bloqueo

            elif evento.key == pygame.K_n:
                accion_cfg("Semilla")

            elif evento.key == pygame.K_c and boton_habilitado("Comparar busquedas"):
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

    avanzar_preparacion_alt()
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
    if configuracion_ventana is not None:
        configuracion_ventana.refrescar()

    # ========================================================
    # DIBUJAR EL MAPA
    # ========================================================

    pantalla.fill(ui.BG)
    pantalla.set_clip(pygame.Rect(0,0,ANCHO,ALTO-PANEL))

    pantalla.blit(
        mapa_escalado,
        (
            int(desplazamiento_x),
            int(desplazamiento_y)
        )
    )

    # El recorrido permanece sobre todas las vistas y debajo del NPC.
    dibujar_resultado()
    dibujar_rastro()

    # Obstaculos dinamicos: los de "atras" van bajo el NPC, los de "adelante" sobre el.
    dibujar_zonas_bloqueo()
    dibujar_obstaculos(False)

    # Dibujar el aventurero encima del mapa.
    dibujar_npc()
    dibujar_obstaculos(True)

    # Dibujar el rectángulo de referencia de los pies.
    dibujar_hitbox_pies()
    dibujar_efectos()

    # ========================================================
    # PANEL INFERIOR
    # ========================================================

    pantalla.set_clip(None)
    if mensaje:
        ui.box(pantalla,pygame.Rect(20,18,650,34),ui.PANEL,9)
        ui.text(pantalla,mensaje,(32,26),ui.TEXT,13,width=626)
    dibujar_panel()

    pygame.display.flip()


# ============================================================
# 12. CERRAR PYGAME
# ============================================================

interrumpir_recorrido("Interrumpido al cerrar")
pygame.quit()