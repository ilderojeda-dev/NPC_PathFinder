"""Carga del mapa y matrices de transitabilidad; conserva una sola instancia de cada matriz."""

from obstaculos_dinamicos import GestorObstaculosDinamicos
import numpy as np
from time import perf_counter
import pygame

class Mapa:
    """Servicio con referencia a la aplicacion; no copia matrices ni mantiene globals."""

    def __init__(self, app):
        self.app = app

    def inicializar(self):
        if not self.app.RUTA_IMAGEN.exists():
            raise FileNotFoundError(f'No se encontro la imagen del mapa: {self.app.RUTA_IMAGEN.name}')
        self.app.imagen_original = pygame.image.load(str(self.app.RUTA_IMAGEN)).convert()
        self.app.ancho_mapa = self.app.imagen_original.get_width()
        self.app.alto_mapa = self.app.imagen_original.get_height()
        if not self.app.RUTA_MASCARA.exists():
            raise FileNotFoundError(f'No se encontro la mascara de transitabilidad: {self.app.RUTA_MASCARA.name}. Coloca este PNG junto al archivo Python.')
        self.app.mascara_original = pygame.image.load(str(self.app.RUTA_MASCARA)).convert_alpha()
        if self.app.mascara_original.get_masks()[3] == 0:
            raise ValueError('La mascara no contiene un canal alfa real. Se necesita un PNG con transparencia.')
        self.app.ancho_mascara = self.app.mascara_original.get_width()
        self.app.alto_mascara = self.app.mascara_original.get_height()
        if self.app.ancho_mascara != self.app.ancho_mapa or self.app.alto_mascara != self.app.alto_mapa:
            raise ValueError(f'La mascara y el mapa tienen dimensiones diferentes. Mapa: {self.app.ancho_mapa}x{self.app.alto_mapa}; mascara: {self.app.ancho_mascara}x{self.app.alto_mascara}. Corrige la máscara para que tenga el mismo tamaño y alineación.')
        # Pygame usa [x,y]; las matrices del motor usan [y,x].
        self.app.alfa_pixeles = pygame.surfarray.array_alpha(self.app.mascara_original)
        self.app.alfa_pixeles = np.transpose(self.app.alfa_pixeles, (1, 0))
        self.app.matriz_transitabilidad = np.where(self.app.alfa_pixeles <= self.app.ALPHA_UMBRAL,
            1,
            0).astype(np.uint8)
        self.app._t_prep = perf_counter()
        self.app.matriz_posiciones_validas_estatica = self.crear_matriz_posiciones_validas()
        self.app.TIEMPO_PREPARACION_ESTATICA = perf_counter() - self.app._t_prep
        self.app.SEMILLA_INICIAL = 2024
        self.app.gestor_obstaculos = GestorObstaculosDinamicos(self.app.matriz_transitabilidad,
            self.app.matriz_posiciones_validas_estatica,
            self.app.ANCHO_HITBOX_PIES,
            self.app.ALTO_HITBOX_PIES,
            self.app.SEMILLA_INICIAL)
        # Misma matriz efectiva para busquedas, colisiones y visualizacion.
        self.app.matriz_posiciones_validas = self.app.gestor_obstaculos.efectiva
        self.app.navegacion.preparar_motor()
        self.app.cantidad_validas = int(np.count_nonzero(self.app.matriz_posiciones_validas))
        self.app.cantidad_validas_estatica = self.app.cantidad_validas
        self.app.cantidad_invalidas = int(self.app.matriz_posiciones_validas.size) - self.app.cantidad_validas
        self.app.porcentaje_validas = 100 * self.app.cantidad_validas / self.app.matriz_posiciones_validas.size
        self.app.colores_posiciones = np.empty((*self.app.matriz_posiciones_validas.shape, 3), dtype=np.uint8)
        self.app.colores_posiciones[:] = (220, 55, 55)
        self.app.colores_posiciones[self.app.matriz_posiciones_validas == 1] = (35, 190, 85)
        self.app.imagen_posiciones_validas = pygame.surfarray.make_surface(self.app.colores_posiciones.transpose(1,
            0,
            2))
        self.app.cantidad_transitable = int(np.count_nonzero(self.app.matriz_transitabilidad == 1))
        self.app.cantidad_obstaculos = int(np.count_nonzero(self.app.matriz_transitabilidad == 0))
        self.app.total_celdas = int(self.app.matriz_transitabilidad.size)
        self.app.porcentaje_transitable = self.app.cantidad_transitable * 100 / self.app.total_celdas
        self.app.colores_binarios = np.zeros((self.app.alto_mapa, self.app.ancho_mapa, 3), dtype=np.uint8)
        self.app.colores_binarios[self.app.matriz_transitabilidad == 1] = (35, 190, 85)
        self.app.colores_binarios[self.app.matriz_transitabilidad == 0] = (220, 55, 55)
        self.app.imagen_binaria_rgb = np.transpose(self.app.colores_binarios, (1, 0, 2))
        self.app.imagen_transitabilidad = pygame.surfarray.make_surface(self.app.imagen_binaria_rgb)

    def crear_matriz_posiciones_validas(self):
        """Comprueba los 105 pixeles con sumas acumuladas, en O(alto*ancho)."""
        alto, ancho = self.app.matriz_transitabilidad.shape
        validas = np.zeros((alto, ancho), dtype=np.uint8)
        h, w = (self.app.ALTO_HITBOX_PIES, self.app.ANCHO_HITBOX_PIES)
        if alto < h or ancho < w:
            return validas
        acumulada = np.pad(self.app.matriz_transitabilidad.astype(np.int32), ((1, 0), (1, 0)))
        acumulada = acumulada.cumsum(axis=0).cumsum(axis=1)
        sumas = acumulada[h:, w:] - acumulada[:-h, w:] - acumulada[h:, :-w] + acumulada[:-h, :-w]
        validas[h // 2:alto - h // 2, w // 2:ancho - w // 2] = sumas == h * w
        return validas

    def es_posicion_valida(self, x, y):
        alto, ancho = self.app.matriz_posiciones_validas.shape
        return 0 <= x < ancho and 0 <= y < alto and bool(self.app.matriz_posiciones_validas[y, x])

    def obtener_vecinos(self, x, y):
        """Grafo implicito: coordenadas (x,y), matriz [y,x], sin diagonales."""
        if not self.es_posicion_valida(x, y):
            return []
        return [(nx, ny) for nx,
            ny in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)) if self.es_posicion_valida(nx, ny)]

    def refrescar_imagen_posiciones(self, region):
        """Actualiza solo la ventana afectada de la vista V (posiciones validas).
    Naranja = valida en el mapa estatico pero bloqueada por un dinamico."""
        x0, y0, x1, y1 = region
        efectiva = self.app.matriz_posiciones_validas[y0:y1, x0:x1]
        colores = np.empty((y1 - y0, x1 - x0, 3), dtype=np.uint8)
        colores[:] = (220, 55, 55)
        colores[efectiva == 1] = (35, 190, 85)
        colores[(self.app.matriz_posiciones_validas_estatica[y0:y1, x0:x1] == 1) & (efectiva == 0)] = (255, 150, 0)
        pixeles = pygame.surfarray.pixels3d(self.app.imagen_posiciones_validas)
        pixeles[x0:x1, y0:y1] = colores.transpose(1, 0, 2)
        del pixeles

    def registrar_cambio_mapa(self, info, rescalar=True):
        self.app.cantidad_validas += info['delta']
        self.app.cantidad_invalidas = int(self.app.matriz_posiciones_validas.size) - self.app.cantidad_validas
        self.app.porcentaje_validas = 100 * self.app.cantidad_validas / self.app.matriz_posiciones_validas.size
        self.refrescar_imagen_posiciones(info['region'])
        if rescalar and self.app.mostrar_posiciones_validas:
            self.app.camara.actualizar_vista()
