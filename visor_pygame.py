"""Visor independiente. No calcula colisiones a partir de los colores."""
import math
from pathlib import Path
import pygame

from logica_pathfinding import leer_mapa, convertir_a_matriz
from terrenos import crear_textura_mapa

TILE = 8
HUD = 106
INICIO = (100, 200)
OBJETIVO = (420, 300)


class Camara:
    def __init__(self, mundo, ventana):
        self.mundo = mundo
        self.ventana = ventana
        self.ajustar()

    def ajustar(self):
        self.zoom = min(self.ventana[0] / self.mundo[0],
                        self.ventana[1] / self.mundo[1])
        self.x = self.y = 0.0
        self.limitar()

    def limitar(self):
        for atributo, dimension, espacio in zip(('x', 'y'), self.mundo, self.ventana):
            visible = espacio / self.zoom
            valor = ((dimension - visible) / 2 if visible >= dimension else
                     max(0, min(getattr(self, atributo), dimension - visible)))
            setattr(self, atributo, valor)

    def a_mundo(self, posicion):
        return (self.x + posicion[0] / self.zoom,
                self.y + posicion[1] / self.zoom)

    def a_pantalla(self, posicion):
        return ((posicion[0] - self.x) * self.zoom,
                (posicion[1] - self.y) * self.zoom)

    def acercar(self, factor, ancla):
        wx, wy = self.a_mundo(ancla)
        minimo = min(self.ventana[0] / self.mundo[0],
                     self.ventana[1] / self.mundo[1])
        self.zoom = max(minimo, min(8.0, self.zoom * factor))
        self.x = wx - ancla[0] / self.zoom
        self.y = wy - ancla[1] / self.zoom
        self.limitar()

    def mover(self, dx, dy):
        self.x += dx / self.zoom
        self.y += dy / self.zoom
        self.limitar()

    def celda(self, posicion, filas, columnas):
        x, y = self.a_mundo(posicion)
        fila, columna = math.floor(y / TILE), math.floor(x / TILE)
        if 0 <= fila < filas and 0 <= columna < columnas:
            return fila, columna
        return None


def dibujar_mundo(pantalla, mundo, camara):
    """Escala solo el recorte visible, nunca una superficie gigante ampliada."""
    pantalla.fill((15, 19, 23))
    w, h = camara.ventana
    recorte = pygame.Rect(math.floor(camara.x), math.floor(camara.y),
                          math.ceil(w / camara.zoom) + 2,
                          math.ceil(h / camara.zoom) + 2).clip(mundo.get_rect())
    if recorte.width and recorte.height:
        destino = (max(1, round(recorte.width * camara.zoom)),
                   max(1, round(recorte.height * camara.zoom)))
        # scale conserva los pixeles; no mezcla agua, bosque y cesped.
        imagen = pygame.transform.scale(mundo.subsurface(recorte), destino)
        pantalla.blit(imagen, tuple(round(v) for v in
                                    camara.a_pantalla(recorte.topleft)))


def dibujar_interfaz(pantalla, fuente, camara, mapa, matriz, raton):
    altura = camara.ventana[1]
    for nodo, color, nombre in ((INICIO, (255, 226, 80), 'Inicio'),
                                (OBJETIVO, (255, 105, 105), 'Objetivo')):
        fila, columna = nodo
        if 0 <= fila < len(mapa) and 0 <= columna < len(mapa[0]):
            x, y = camara.a_pantalla(((columna + .5) * TILE, (fila + .5) * TILE))
            if 0 <= x < pantalla.get_width() and 0 <= y < altura:
                pygame.draw.circle(pantalla, (10, 10, 10), (round(x), round(y)), 8)
                pygame.draw.circle(pantalla, color, (round(x), round(y)), 5)
                pantalla.blit(fuente.render(nombre, True, color), (x + 10, y - 10))
    celda = camara.celda(raton, len(mapa), len(mapa[0])) if raton[1] < altura else None
    detalle = 'Cursor fuera del mapa'
    if celda is not None:
        fila, columna = celda
        estado = 'TRANSITABLE' if matriz[fila][columna] else 'BLOQUEADO'
        detalle = f'Fila {fila} | Columna {columna} | Simbolo {mapa[fila][columna]} | {estado}'
    pygame.draw.rect(pantalla, (20, 26, 32), (0, altura, pantalla.get_width(), HUD))
    textos = [f'DARK FOREST | {len(mapa)} x {len(mapa[0])} celdas | {TILE * camara.zoom:.1f} px/celda',
              'Rueda: zoom | Arrastrar: mover | WASD / flechas: mover | R: mapa completo | Esc: salir',
              '. Pasto: transitable | T Bosque / W Agua / @ Exterior: bloqueados', detalle]
    for i, texto in enumerate(textos):
        pantalla.blit(fuente.render(texto, True, (225, 232, 218)), (14, altura + 8 + i * 23))


def main():
    ruta = Path(__file__).resolve().parent / 'DataSet' / 'darkforest.map'
    mapa = leer_mapa(ruta)
    if len(mapa) != 512 or any(len(fila) != 512 for fila in mapa):
        raise ValueError('Dark Forest debe conservar sus 512 x 512 celdas.')
    matriz = convertir_a_matriz(mapa)
    textura = crear_textura_mapa(mapa)
    pygame.display.init()
    pygame.font.init()
    try:
        pantalla = pygame.display.set_mode((1100, 850), pygame.RESIZABLE)
        pygame.display.set_caption('NPC PathFinder - Dark Forest')
        fuente = pygame.font.Font(None, 22)
        # NumPy indexa [fila, columna]; Pygame recibe ancho, alto.
        mundo = pygame.image.frombuffer(textura.tobytes(),
                                       (textura.shape[1], textura.shape[0]), 'RGB').convert()
        del textura
        camara = Camara(mundo.get_size(), (pantalla.get_width(), pantalla.get_height() - HUD))
        reloj = pygame.time.Clock()
        activo, arrastrando = True, False
        while activo:
            dt = min(reloj.tick(60) / 1000, .05)
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    activo = False
                elif evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_ESCAPE:
                        activo = False
                    elif evento.key == pygame.K_r:
                        camara.ajustar()
                elif evento.type == pygame.VIDEORESIZE:
                    pantalla = pygame.display.set_mode((max(700, evento.w), max(350, evento.h)), pygame.RESIZABLE)
                    camara.ventana = (pantalla.get_width(), pantalla.get_height() - HUD)
                    camara.acercar(1, (0, 0))
                elif evento.type == pygame.MOUSEWHEEL:
                    posicion = pygame.mouse.get_pos()
                    if posicion[1] < camara.ventana[1]:
                        camara.acercar(1.25 ** max(-10, min(10, evento.y)), posicion)
                elif evento.type == pygame.MOUSEBUTTONDOWN and evento.button in (1, 2, 3):
                    arrastrando = evento.pos[1] < camara.ventana[1]
                elif evento.type == pygame.MOUSEBUTTONUP and evento.button in (1, 2, 3):
                    arrastrando = False
                elif evento.type == pygame.WINDOWFOCUSLOST:
                    arrastrando = False
                elif evento.type == pygame.MOUSEMOTION and arrastrando:
                    camara.mover(-evento.rel[0], -evento.rel[1])
            teclas = pygame.key.get_pressed()
            dx = int(teclas[pygame.K_d] or teclas[pygame.K_RIGHT]) - int(teclas[pygame.K_a] or teclas[pygame.K_LEFT])
            dy = int(teclas[pygame.K_s] or teclas[pygame.K_DOWN]) - int(teclas[pygame.K_w] or teclas[pygame.K_UP])
            if dx or dy:
                camara.mover(dx * 600 * dt, dy * 600 * dt)
            dibujar_mundo(pantalla, mundo, camara)
            dibujar_interfaz(pantalla, fuente, camara, mapa, matriz, pygame.mouse.get_pos())
            pygame.display.flip()
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
