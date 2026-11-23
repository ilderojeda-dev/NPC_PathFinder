"""Sprite, hitbox, movimiento y dibujo del NPC y su rastro."""

import pygame
import interfaz_pygame as ui

class NPC:
    """Servicio con referencia a la aplicacion; no copia matrices ni mantiene globals."""

    def __init__(self, app):
        self.app = app

    def inicializar(self):
        if not self.app.RUTA_SPRITE.exists():
            raise FileNotFoundError(f'No se encontro el sprite: {self.app.RUTA_SPRITE.name}')
        self.app.hoja_sprites = pygame.image.load(str(self.app.RUTA_SPRITE)).convert_alpha()
        self.app.COLUMNAS_SPRITE = 4
        self.app.FILAS_SPRITE = 5
        if self.app.hoja_sprites.get_width() % self.app.COLUMNAS_SPRITE != 0:
            raise ValueError('El ancho del sprite no se puede dividir exactamente en 4 columnas.')
        if self.app.hoja_sprites.get_height() % self.app.FILAS_SPRITE != 0:
            raise ValueError('El alto del sprite no se puede dividir exactamente en 5 filas.')
        self.app.ancho_frame_original = self.app.hoja_sprites.get_width() // self.app.COLUMNAS_SPRITE
        self.app.alto_frame_original = self.app.hoja_sprites.get_height() // self.app.FILAS_SPRITE
        if self.app.ancho_frame_original != self.app.ANCHO_NPC or self.app.alto_frame_original != self.app.ALTO_NPC:
            raise ValueError(f'Cada cuadro deberia medir {self.app.ANCHO_NPC}x{self.app.ALTO_NPC}, pero mide {self.app.ancho_frame_original}x{self.app.alto_frame_original}.')
        self.app.filas_direccion = {'abajo': 0, 'izquierda': 1, 'derecha': 2, 'arriba': 3}
        self.app.sprites_npc = {}
        for self.app.direccion, self.app.fila in self.app.filas_direccion.items():
            self.app.sprites_npc[self.app.direccion] = []
            for self.app.columna in range(self.app.COLUMNAS_SPRITE):
                self.app.rectangulo = pygame.Rect(self.app.columna * self.app.ancho_frame_original,
                    self.app.fila * self.app.alto_frame_original,
                    self.app.ancho_frame_original,
                    self.app.alto_frame_original)
                self.app.frame = self.app.hoja_sprites.subsurface(self.app.rectangulo).copy()
                self.app.sprites_npc[self.app.direccion].append(self.app.frame)
        self.app.sprites_idle = []
        for self.app.columna in range(self.app.COLUMNAS_SPRITE):
            self.app.rectangulo = pygame.Rect(self.app.columna * self.app.ancho_frame_original,
                4 * self.app.alto_frame_original,
                self.app.ancho_frame_original,
                self.app.alto_frame_original)
            self.app.frame = self.app.hoja_sprites.subsurface(self.app.rectangulo).copy()
            self.app.sprites_idle.append(self.app.frame)
        self.app.npc_x = 450
        self.app.npc_y = 450
        self.app.resto_movimiento = 0.0
        self.app.sentido_movimiento = (0, 0)
        self.app.rastro_puntos = []
        self.app.rastro_cache = (0, [])
        self.app.direccion_npc = 'abajo'
        self.app.indice_frame_npc = 0
        self.app.tiempo_animacion_npc = 0.0
        self.app.moviendo_npc = False
        self.app.mostrar_hitbox_pies = False

    def centro_hitbox(self):
        # npc_y es el borde inferior: el centro de los pies queda cuatro pixeles arriba.
        return (int(self.app.npc_x), int(self.app.npc_y) - (self.app.ALTO_HITBOX_PIES // 2 + 1))

    def marcar_rastro(self, x, y):
        """Registra cada nodo realmente visitado; se dibuja como linea vectorial."""
        if not self.app.rastro_puntos or self.app.rastro_puntos[-1] != (x, y):
            self.app.rastro_puntos.append((x, y))

    def vertices_ortogonales(self, puntos):
        """Reduce nodos contiguos a sus esquinas: la linea se ve igual con menos puntos."""
        if len(puntos) < 3:
            return list(puntos)
        salida = [puntos[0]]
        for i in range(1, len(puntos) - 1):
            a, b, c = (puntos[i - 1], puntos[i], puntos[i + 1])
            if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
                salida.append(b)
        salida.append(puntos[-1])
        return salida

    def dibujar_rastro(self):
        """Recorrido del NPC como polilinea (reemplaza la capa de pixeles)."""
        if len(self.app.rastro_puntos) < 2:
            return
        if self.app.rastro_cache[0] != len(self.app.rastro_puntos):
            self.app.rastro_cache = (len(self.app.rastro_puntos),
                self.vertices_ortogonales(self.app.rastro_puntos))
        ui.polilinea(self.app.pantalla,
            self.app.camara.a_pantalla(self.app.rastro_cache[1]),
            (255, 96, 84),
            max(2, self.app.camara.ancho_linea() - 1),
            grosor_borde=1)

    def mover_npc_con_colisiones(self, dx, dy, distancia):
        if dx:
            dy = 0
        sentido = (dx, dy)
        if sentido != self.app.sentido_movimiento:
            self.app.resto_movimiento = 0.0
            self.app.sentido_movimiento = sentido
        if not dx and (not dy):
            self.app.resto_movimiento = 0.0
            return False
        self.app.resto_movimiento += distancia
        pasos = int(self.app.resto_movimiento)
        self.app.resto_movimiento -= pasos
        x, y = self.centro_hitbox()
        movido = False
        for _ in range(pasos):
            nx, ny = (x + dx, y + dy)
            if not self.app.mapa.es_posicion_valida(nx, ny):
                self.app.resto_movimiento = 0.0
                break
            x, y = (nx, ny)
            self.marcar_rastro(x, y)
            movido = True
        self.app.npc_x = x
        self.app.npc_y = y + self.app.ALTO_HITBOX_PIES // 2 + 1
        return movido

    def actualizar_npc(self, dt):
        self.app.estadisticas_registro.actualizar_reloj_recorrido()
        caminaba = self.app.moviendo_npc
        self.app.moviendo_npc = False
        if self.app.animando and (not self.app.pausa_replan):
            self.app.sesion['t_animacion'] += dt
            self.app.acumulado_ruta += self.app.VELOCIDAD_NPC * dt
            while self.app.acumulado_ruta >= 1 and self.app.indice_ruta < len(self.app.ruta_encontrada) - 1:
                if self.app.gestor_obstaculos.obstaculos and self.app.navegacion.detectar_obstaculo_cercano() is not None:
                    break
                x, y = self.centro_hitbox()
                nx, ny = self.app.ruta_encontrada[self.app.indice_ruta + 1]
                dx, dy = (nx - x, ny - y)
                if abs(dx) + abs(dy) != 1 or not self.app.mapa.es_posicion_valida(nx, ny):
                    self.app.animando = False
                    self.app.mensaje = 'Recorrido detenido: paso no valido.'
                    self.app.estadisticas_registro.cerrar_recorrido('Interrumpido: paso no valido')
                    break
                self.mover_npc_con_colisiones(dx, dy, 1)
                if self.centro_hitbox() != (nx, ny):
                    self.app.animando = False
                    self.app.mensaje = 'Recorrido detenido por colision.'
                    self.app.estadisticas_registro.cerrar_recorrido('Interrumpido: colision')
                    break
                self.app.direccion_npc = 'derecha' if dx > 0 else 'izquierda' if dx < 0 else 'abajo' if dy > 0 else 'arriba'
                self.app.indice_ruta += 1
                self.app.acumulado_ruta -= 1
                self.app.sesion['pasos'] += 1
                self.app.sesion['rutas'][-1]['realizados'] += 1
                self.app.pasos_desde_obstaculo += 1
            if self.app.indice_ruta == len(self.app.ruta_encontrada) - 1:
                self.app.animando = False
                self.app.mensaje = 'Destino alcanzado.'
                self.app.estadisticas_registro.cerrar_recorrido('Destino alcanzado')
                self.app.sesion['rutas'][-1]['completada'] = True
                self.app.sesion['longitud_final'] = self.app.sesion['pasos']
            self.app.estadisticas_registro.actualizar_reloj_recorrido()
            self.app.moviendo_npc = self.app.animando
        if caminaba != self.app.moviendo_npc:
            self.app.indice_frame_npc = 0
            self.app.tiempo_animacion_npc = 0.0
        self.app.tiempo_animacion_npc += dt
        intervalo = self.app.INTERVALO_ANIMACION if self.app.moviendo_npc else self.app.INTERVALO_IDLE
        while self.app.tiempo_animacion_npc >= intervalo:
            self.app.indice_frame_npc = (self.app.indice_frame_npc + 1) % 4
            self.app.tiempo_animacion_npc -= intervalo

    def dibujar_npc(self):
        if self.app.inicio_busqueda is None:
            return
        if self.app.moviendo_npc:
            frame = self.app.sprites_npc[self.app.direccion_npc][self.app.indice_frame_npc]
        else:
            frame = self.app.sprites_idle[self.app.indice_frame_npc]
        ancho = max(1, int(self.app.ANCHO_NPC * self.app.zoom))
        alto = max(1, int(self.app.ALTO_NPC * self.app.zoom))
        frame_escalado = pygame.transform.scale(frame, (ancho, alto))
        centro_x, centro_y = self.app.camara.centro_pies_pantalla()
        escala_y = self.app.mapa_escalado.get_height() / self.app.alto_mapa
        posicion_x = round(centro_x - ancho / 2)
        posicion_y = round(centro_y + self.app.ALTO_HITBOX_PIES / 2 * escala_y - alto)
        self.app.pantalla.blit(frame_escalado, (posicion_x, posicion_y))

    def dibujar_hitbox_pies(self):
        if self.app.inicio_busqueda is None or not self.app.mostrar_hitbox_pies:
            return
        centro_x, centro_y = self.app.camara.centro_pies_pantalla()
        sx = self.app.mapa_escalado.get_width() / self.app.ancho_mapa
        sy = self.app.mapa_escalado.get_height() / self.app.alto_mapa
        izquierda = round(centro_x - self.app.ANCHO_HITBOX_PIES * sx / 2)
        arriba = round(centro_y - self.app.ALTO_HITBOX_PIES * sy / 2)
        derecha = round(centro_x + self.app.ANCHO_HITBOX_PIES * sx / 2)
        abajo = round(centro_y + self.app.ALTO_HITBOX_PIES * sy / 2)
        ancho, alto = (max(1, derecha - izquierda), max(1, abajo - arriba))
        rect_pies = pygame.Rect(izquierda, arriba, ancho, alto)
        relleno = pygame.Surface((ancho, alto), pygame.SRCALPHA)
        relleno.fill((255, 40, 40, 65))
        self.app.pantalla.blit(relleno, rect_pies.topleft)
        grosor = max(1, int(2 * self.app.zoom))
        pygame.draw.rect(self.app.pantalla, (255, 70, 70), rect_pies, grosor)

    def ubicar_en_inicio(self):
        self.app.camara.detener_seguimiento()
        self.app.npc_x, y = self.app.inicio_busqueda
        self.app.npc_y = y + self.app.ALTO_HITBOX_PIES // 2 + 1
        self.app.resto_movimiento = self.app.acumulado_ruta = 0.0
        self.app.sentido_movimiento = (0, 0)
        self.app.indice_ruta = 0
        self.app.moviendo_npc = False
        self.app.indice_frame_npc = 0
        self.app.tiempo_animacion_npc = 0.0
        self.app.rastro_puntos.clear()
        self.marcar_rastro(*self.app.inicio_busqueda)
