"""
Obstaculos dinamicos para el proyecto de busqueda de rutas (BFS / A*).

Este modulo NO conoce Pygame mas alla de dibujar los sprites; toda la logica
de transitabilidad trabaja unicamente con arrays de NumPy.

Arquitectura de tres capas
--------------------------
1. ``estatica``  : matriz de posiciones validas original. Nunca se modifica.
2. ``mascara``   : contador (uint16) de cuantos obstaculos dinamicos invalidan
                   cada posicion de centro de hitbox.
3. ``efectiva``  : ``estatica & (mascara == 0)``. Es la unica matriz que
                   consultan BFS, A*, las colisiones y el visualizador.

Colocar o retirar un obstaculo solo recalcula la ventana rectangular que el
obstaculo inflado por la hitbox puede afectar: O(area del obstaculo), nunca
O(alto * ancho) del mapa.

Convencion de coordenadas: matrices [y, x]; puntos (x, y).
"""

import random
from dataclasses import dataclass
from time import perf_counter

import numpy as np
import pygame


# ------------------------------------------------------------------
# Catalogo de obstaculos: (tipo, ancho_huella, alto_huella) en pixeles del mapa
# ------------------------------------------------------------------

CATALOGO = {
    "Pequeno": [("roca", 14, 11), ("arbusto", 16, 12)],
    "Mediano": [("roca", 24, 18), ("arbusto", 26, 20), ("tronco", 34, 12)],
    "Grande": [("roca", 36, 28), ("tronco", 48, 14), ("arbusto", 38, 28)],
}
CATALOGO["Mixto"] = (CATALOGO["Pequeno"] + CATALOGO["Mediano"]
                     + CATALOGO["Grande"])
TAMANOS = ("Pequeno", "Mediano", "Grande", "Mixto")

MODO_RUTA = "En la ruta"      # El obstaculo cae sobre el tramo que falta.
MODO_LIBRE = "Libre"          # Cualquier lugar valido; puede no afectar.
MODOS = (MODO_RUTA, MODO_LIBRE)

# Margenes de seguridad (en pixeles) medidos sobre la zona inflada.
MARGEN_NPC = 12          # Nunca aparece debajo ni pegado al NPC.
MARGEN_DESTINO = 10      # Nunca bloquea el destino ni su entorno inmediato.
SEPARACION_OBSTACULOS = 2
DISTANCIA_MIN_DESTINO = 16   # Nodos antes del final de la ruta.


@dataclass
class ObstaculoDinamico:
    id: int
    tipo: str
    x: int
    y: int
    ancho: int
    alto: int
    region: tuple          # (x0, y0, x1, y1): centros de hitbox invalidados
    sprite: pygame.Surface
    paso: int = 0          # Paso del NPC en el que aparecio.
    cache_tamano: tuple = None
    cache_sprite: pygame.Surface = None

    @property
    def huella(self):
        return (self.x, self.y, self.ancho, self.alto)

    def descripcion(self):
        return f"{self.tipo}({self.x},{self.y},{self.ancho}x{self.alto})"


@dataclass
class EventoObstaculo:
    """Obstaculo planificado para una comparacion reproducible."""
    paso: int
    tipo: str
    x: int
    y: int
    ancho: int
    alto: int
    semilla_sprite: int


# ------------------------------------------------------------------
# Sprites procedurales (pixel art simple, sin archivos externos)
# ------------------------------------------------------------------

def crear_sprite(tipo, ancho, alto, semilla=0):
    r = random.Random(semilla)
    s = pygame.Surface((ancho, alto), pygame.SRCALPHA)
    if tipo == "tronco":
        radio = max(2, alto // 2)
        pygame.draw.rect(s, (58, 34, 16), (0, 0, ancho, alto), border_radius=radio)
        pygame.draw.rect(s, (128, 80, 38), (1, 1, ancho - 2, alto - 2),
                         border_radius=max(1, radio - 1))
        for yy in range(3, alto - 2, 3):
            pygame.draw.line(s, (96, 58, 27), (alto // 2, yy), (ancho - 3, yy))
        for _ in range(max(2, ancho // 12)):
            xx = r.randint(alto, max(alto, ancho - 4))
            pygame.draw.line(s, (170, 118, 62), (xx, 2), (xx + 2, 2))
        pygame.draw.ellipse(s, (58, 34, 16), (0, 0, max(4, int(alto * .8)), alto))
        pygame.draw.ellipse(s, (205, 158, 96),
                            (1, 1, max(2, int(alto * .8) - 2), alto - 2))
        pygame.draw.ellipse(s, (160, 112, 60),
                            (2, 2, max(1, int(alto * .8) - 4), max(1, alto - 4)), 1)
    elif tipo == "arbusto":
        pygame.draw.ellipse(s, (20, 70, 30), (0, 0, ancho, alto))
        n = max(4, ancho // 5)
        for _ in range(n):
            rad = r.randint(max(2, alto // 4), max(3, alto // 2 - 1))
            cx = r.randint(rad, max(rad, ancho - rad))
            cy = r.randint(rad, max(rad, alto - rad))
            pygame.draw.circle(s, (32, 100, 44), (cx, cy), rad)
        for _ in range(n):
            rad = r.randint(max(1, alto // 5), max(2, alto // 3))
            cx = r.randint(rad + 1, max(rad + 1, ancho - rad - 1))
            cy = r.randint(rad, max(rad, alto // 2 + 1))
            pygame.draw.circle(s, (70, 160, 66), (cx, cy), rad)
            pygame.draw.circle(s, (112, 200, 92), (cx - 1, cy - 1), max(1, rad // 2))
        for _ in range(max(2, ancho // 9)):
            px, py = r.randint(2, ancho - 3), r.randint(2, alto - 3)
            s.set_at((px, py), (230, 90, 120))
    else:  # roca
        contorno, sombra = (50, 50, 58), (84, 84, 96)
        base, luz = (122, 122, 132), (176, 176, 186)
        pygame.draw.ellipse(s, contorno, (0, 0, ancho, alto))
        pygame.draw.ellipse(s, sombra, (1, 1, ancho - 2, alto - 2))
        pygame.draw.ellipse(s, base, (1, 1, max(2, ancho - 2 - max(1, ancho // 5)),
                                      max(2, alto - 2 - max(1, alto // 4))))
        pygame.draw.ellipse(s, luz, (max(2, ancho // 5), max(1, alto // 7) + 1,
                                     max(2, ancho // 3), max(2, alto // 4)))
        for _ in range(max(1, ancho // 12)):
            x0 = r.randint(ancho // 4, 3 * ancho // 4)
            y0 = r.randint(alto // 3, 2 * alto // 3)
            pygame.draw.line(s, contorno, (x0, y0),
                             (x0 + r.randint(-3, 3), y0 + r.randint(2, 4)))
    return s


# ------------------------------------------------------------------
# Gestor
# ------------------------------------------------------------------

class GestorObstaculosDinamicos:

    def __init__(self, transitabilidad, validas_estaticas,
                 ancho_hitbox, alto_hitbox, semilla=0):
        self.transitabilidad = transitabilidad
        self.estatica = validas_estaticas
        self.alto, self.ancho = validas_estaticas.shape
        self.mascara = np.zeros(validas_estaticas.shape, dtype=np.uint16)
        # La efectiva es un array propio que se modifica SIEMPRE en el lugar,
        # para que cualquier referencia externa siga siendo valida.
        self.efectiva = validas_estaticas.copy()
        # La hitbox ocupa [c - ext_izq, c + ext_der] x [c - ext_arr, c + ext_aba]
        self.ext_izq = ancho_hitbox // 2
        self.ext_der = ancho_hitbox - 1 - self.ext_izq
        self.ext_arr = alto_hitbox // 2
        self.ext_aba = alto_hitbox - 1 - self.ext_arr
        self.obstaculos = []
        self._id = 1
        self.rng = random.Random(semilla)

    # ---------------- geometria ----------------

    def region_bloqueada(self, x, y, ancho, alto):
        """Ventana (x0, y0, x1, y1) [fin exclusivo] de centros de hitbox que
        tocarian la huella (x, y, ancho, alto), recortada al mapa."""
        x0 = max(0, x - self.ext_der)
        x1 = min(self.ancho, x + ancho + self.ext_izq)
        y0 = max(0, y - self.ext_aba)
        y1 = min(self.alto, y + alto + self.ext_arr)
        return x0, y0, x1, y1

    def huella_libre(self, x, y, ancho, alto):
        """Toda la huella esta sobre terreno estaticamente transitable."""
        if x < 0 or y < 0 or x + ancho > self.ancho or y + alto > self.alto:
            return False
        return bool(self.transitabilidad[y:y + alto, x:x + ancho].all())

    def _solapa(self, x, y, ancho, alto, extra=()):
        m = SEPARACION_OBSTACULOS
        huellas = [o.huella for o in self.obstaculos]
        huellas.extend(extra)
        for ox, oy, ow, oh in huellas:
            if (x < ox + ow + m and ox < x + ancho + m
                    and y < oy + oh + m and oy < y + alto + m):
                return True
        return False

    def _cerca(self, x, y, ancho, alto, punto, margen):
        px, py = punto
        return (x - self.ext_der - margen <= px < x + ancho + self.ext_izq + margen
                and y - self.ext_aba - margen <= py < y + alto + self.ext_arr + margen)

    def candidato_valido(self, x, y, ancho, alto, npc=None, destino=None,
                         extra=(), min_nodos=1):
        """Reglas de aparicion:
        - Huella completa sobre terreno libre (no sobre obstaculos estaticos).
        - Sin solapar otros obstaculos dinamicos.
        - Zona inflada a MARGEN_NPC del NPC (nunca debajo de el).
        - Zona inflada a MARGEN_DESTINO del destino.
        - Debe invalidar al menos ``min_nodos`` posiciones realmente validas.
        """
        if not self.huella_libre(x, y, ancho, alto):
            return False
        if self._solapa(x, y, ancho, alto, extra):
            return False
        if npc is not None and self._cerca(x, y, ancho, alto, npc, MARGEN_NPC):
            return False
        if destino is not None and self._cerca(x, y, ancho, alto, destino, MARGEN_DESTINO):
            return False
        x0, y0, x1, y1 = self.region_bloqueada(x, y, ancho, alto)
        return int(np.count_nonzero(self.efectiva[y0:y1, x0:x1])) >= min_nodos

    # ---------------- creacion ----------------

    def instanciar(self, tipo, x, y, ancho, alto, semilla_sprite):
        o = ObstaculoDinamico(
            id=self._id, tipo=tipo, x=x, y=y, ancho=ancho, alto=alto,
            region=self.region_bloqueada(x, y, ancho, alto),
            sprite=crear_sprite(tipo, ancho, alto, semilla_sprite))
        self._id += 1
        return o

    def instanciar_evento(self, ev):
        return self.instanciar(ev.tipo, ev.x, ev.y, ev.ancho, ev.alto, ev.semilla_sprite)

    def _nodo_valido_aleatorio(self):
        for _ in range(400):
            x = self.rng.randrange(self.ancho)
            y = self.rng.randrange(self.alto)
            if self.efectiva[y, x]:
                return x, y
        return None

    def proponer(self, modo, tamano, ruta=None, indice=0, npc=None,
                 destino=None, rango=(24, 120), intentos=120):
        """Propone (sin colocar) un obstaculo valido o devuelve None.

        modo="En la ruta": la huella se centra en un nodo del tramo que aun
        no recorre el NPC, entre ``rango[0]`` y ``rango[1]`` nodos por delante,
        de modo que el obstaculo es visible y bloquea de verdad el recorrido.
        modo="Libre": sobre cualquier posicion valida del mapa.
        """
        opciones = CATALOGO[tamano]
        usar_ruta = modo == MODO_RUTA and ruta is not None
        if usar_ruta:
            lo = indice + rango[0]
            hi = min(indice + rango[1], len(ruta) - 1 - DISTANCIA_MIN_DESTINO)
            if hi < lo:
                return None
        for _ in range(intentos):
            tipo, w, h = self.rng.choice(opciones)
            if usar_ruta:
                cx, cy = ruta[self.rng.randint(lo, hi)]
                x = cx - w // 2 + self.rng.randint(-2, 2)
                y = cy - h // 2 + self.rng.randint(-1, 1)
            else:
                nodo = self._nodo_valido_aleatorio()
                if nodo is None:
                    return None
                x, y = nodo[0] - w // 2, nodo[1] - h // 2
            if self.candidato_valido(x, y, w, h, npc, destino):
                return self.instanciar(tipo, x, y, w, h, self.rng.randrange(1 << 30))
        return None

    def crear_guion(self, rutas, cantidad, tamano, destino):
        """Lista de EventoObstaculo reproducible para comparar algoritmos.

        Cada obstaculo se ancla a un nodo de una de las rutas de referencia
        (se alternan) y se dispara tras un numero fijo de pasos del NPC, asi
        ambos algoritmos reciben exactamente los mismos cambios. Debe llamarse
        con el mundo limpio (sin obstaculos colocados)."""
        eventos, huellas = [], []
        opciones = CATALOGO[tamano]
        for i in range(1, cantidad + 1):
            ruta = rutas[(i - 1) % len(rutas)]
            n = len(ruta)
            limite = n - 1 - DISTANCIA_MIN_DESTINO
            j = min(max(round(i * (n - 1) / (cantidad + 1)), 30), limite)
            if j < 30:
                continue
            paso = j - min(self.rng.randint(30, 70), j)
            for _ in range(60):
                tipo, w, h = self.rng.choice(opciones)
                cx, cy = ruta[j]
                x = cx - w // 2 + self.rng.randint(-2, 2)
                y = cy - h // 2 + self.rng.randint(-1, 1)
                if self.candidato_valido(x, y, w, h, None, destino, extra=huellas):
                    eventos.append(EventoObstaculo(paso, tipo, x, y, w, h,
                                                   self.rng.randrange(1 << 30)))
                    huellas.append((x, y, w, h))
                    break
        eventos.sort(key=lambda e: e.paso)
        return eventos

    # ---------------- actualizacion incremental ----------------

    def colocar(self, o):
        """Activa el obstaculo. Devuelve region, delta de posiciones validas
        (negativo) y tiempo empleado en actualizar la matriz efectiva."""
        t0 = perf_counter()
        x0, y0, x1, y1 = o.region
        antes = int(np.count_nonzero(self.efectiva[y0:y1, x0:x1]))
        self.mascara[y0:y1, x0:x1] += 1
        self._recalcular(o.region)
        despues = int(np.count_nonzero(self.efectiva[y0:y1, x0:x1]))
        self.obstaculos.append(o)
        return dict(region=o.region, delta=despues - antes,
                    tiempo=perf_counter() - t0)

    def retirar(self, o):
        t0 = perf_counter()
        x0, y0, x1, y1 = o.region
        antes = int(np.count_nonzero(self.efectiva[y0:y1, x0:x1]))
        self.mascara[y0:y1, x0:x1] -= 1
        self._recalcular(o.region)
        despues = int(np.count_nonzero(self.efectiva[y0:y1, x0:x1]))
        self.obstaculos.remove(o)
        return dict(region=o.region, delta=despues - antes,
                    tiempo=perf_counter() - t0)

    def limpiar(self):
        """Retira todos los obstaculos. Devuelve la lista de cambios."""
        return [self.retirar(o) for o in list(self.obstaculos)]

    def _recalcular(self, region):
        x0, y0, x1, y1 = region
        self.efectiva[y0:y1, x0:x1] = (
            self.estatica[y0:y1, x0:x1] & (self.mascara[y0:y1, x0:x1] == 0))

    # ---------------- deteccion ----------------

    def ruta_bloqueada(self, ruta_np, indice):
        """Indice del primer nodo bloqueado en el tramo que falta
        (ruta_np[indice+1:]) o None si la ruta sigue siendo valida.
        ruta_np es un array (N, 2) con columnas x, y. Vectorizado."""
        if ruta_np is None or indice + 1 >= len(ruta_np):
            return None
        resto = ruta_np[indice + 1:]
        libres = self.efectiva[resto[:, 1], resto[:, 0]]
        if libres.all():
            return None
        return indice + 1 + int(np.argmin(libres))
