"""Tres algoritmos sobre el grafo implicito de posiciones validas [y,x].

BFS Bidireccional y A* + ALT: rutas optimas con costo unitario.
Greedy + ALT: busqueda heuristica sin garantia de optimalidad.
La BFS de LandmarksALT es exclusivamente un auxiliar de preparacion.
"""
from collections import deque
from heapq import heappush, heappop
from time import perf_counter
import numpy as np

ALGORITMOS_DISPONIBLES = ('BFS Bidireccional', 'A* + ALT', 'Greedy + ALT')
LOTE_EXPANSIONES = 2500


def adyacentes(nodo, ancho, total):
    """Vecinos geometricos ortogonales; el algoritmo filtra posiciones bloqueadas."""
    y, x = divmod(nodo, ancho)
    if y: yield nodo - ancho
    if nodo + ancho < total: yield nodo + ancho
    if x: yield nodo - 1
    if x + 1 < ancho: yield nodo + 1


class LandmarksALT:
    def __init__(self, estatica, cantidad=4):
        self.estatica = estatica
        self.cantidad = cantidad
        self.landmarks = []
        self.distancias = []
        self.preparado = False
        self.tiempo = 0.0
        self.preparaciones = 0

    def preparar(self, lote=5000):
        """Una sola preparacion por instancia; cede control entre lotes."""
        if self.preparado:
            return
        t0 = perf_counter()
        self.landmarks.clear(); self.distancias.clear()
        alto, ancho = self.estatica.shape
        libres = self.estatica.reshape(-1)
        total = libres.size
        # Menor distancia a un landmark previo; -1 fuera del mapa transitable.
        cercania = np.where(libres, total + 1, -1).astype(np.int32)
        for i in range(self.cantidad):
            origen = int(np.argmax(cercania)) if total else 0
            if not total or cercania[origen] <= 0:
                break
            dist = np.full(total, -1, dtype=np.int32)
            dist[origen] = 0
            cola = deque([origen]); expandidos = 0
            while cola:
                u = cola.popleft(); siguiente = int(dist[u]) + 1
                for v in adyacentes(u, ancho, total):
                    if libres[v] and dist[v] < 0:
                        dist[v] = siguiente; cola.append(v)
                expandidos += 1
                if expandidos % lote == 0:
                    self.tiempo += perf_counter() - t0
                    yield dict(landmark=i+1, cantidad=self.cantidad, expandidos=expandidos)
                    t0 = perf_counter()
            alcanzados = dist >= 0
            np.minimum(cercania, dist, out=cercania, where=alcanzados)
            self.landmarks.append((origen % ancho, origen // ancho))
            self.distancias.append(dist)
        self.tiempo += perf_counter() - t0
        self.preparado = True
        self.preparaciones += 1

    def heuristica(self, nodo, objetivo, ancho):
        """max(Manhattan, |d(L,n)-d(L,t)|). Ignora pares desconectados.

        Los dinamicos solo eliminan aristas del mapa estatico; al retirarlos
        nunca se crean atajos fuera de este. La cota sigue siendo admisible
        y consistente en cada mapa efectivo.
        """
        h = abs(nodo % ancho - objetivo % ancho) + abs(nodo // ancho - objetivo // ancho)
        for d in self.distancias:
            a, b = int(d[nodo]), int(d[objetivo])
            if a >= 0 and b >= 0:
                h = max(h, abs(a-b))
        return h


class MotorPathfinding:
    def __init__(self, estatica, efectiva, landmarks=4):
        if estatica.shape != efectiva.shape or estatica.ndim != 2:
            raise ValueError('Matrices incompatibles')
        if not estatica.flags.c_contiguous or not efectiva.flags.c_contiguous:
            raise ValueError('Se requieren matrices contiguas [y,x]')
        self.estatica, self.efectiva = estatica, efectiva
        self.alt = LandmarksALT(estatica, landmarks)

    def preparar_alt(self, lote=5000):
        return self.alt.preparar(lote)

    def valida(self, x, y):
        alto, ancho = self.efectiva.shape
        return 0 <= x < ancho and 0 <= y < alto and bool(self.efectiva[y,x])

    def vecinos(self, x, y):
        if not self.valida(x,y):return []
        return [(nx,ny) for nx,ny in ((x,y-1),(x,y+1),(x-1,y),(x+1,y)) if self.valida(nx,ny)]

    def buscar_ruta(self, inicio, objetivo, algoritmo, lote=LOTE_EXPANSIONES):
        if lote < 1:
            raise ValueError('El lote debe ser positivo')
        if algoritmo not in ALGORITMOS_DISPONIBLES:
            raise ValueError('Algoritmo desconocido: ' + algoritmo)
        if algoritmo == 'BFS Bidireccional':
            return (yield from self._buscar_bidireccional(inicio, objetivo, lote))
        if not self.alt.preparado:
            raise RuntimeError('Preparar ALT antes de buscar')
        return (yield from self._buscar_alt(inicio, objetivo, algoritmo, lote))

    def _buscar_alt(self, inicio, objetivo, algoritmo, lote):
        t0=perf_counter();tiempo=0.0
        if not self.valida(*inicio) or not self.valida(*objetivo):
            return dict(ruta=None,descubiertos=0,expandidos=0,tiempo=perf_counter()-t0,estado='Puntos invalidos')
        alto,ancho=self.efectiva.shape;total=alto*ancho
        origen=inicio[1]*ancho+inicio[0];meta=objetivo[1]*ancho+objetivo[0]
        padre=np.full(total,-1,dtype=np.int32);padre[origen]=origen
        greedy=algoritmo=='Greedy + ALT'
        costos=None if greedy else np.full(total,-1,dtype=np.int32)
        if costos is not None:costos[origen]=0
        h=lambda n:self.alt.heuristica(n,meta,ancho)
        cola=[(h(origen),0,origen)];descubiertos=1;expandidos=0;operaciones=0;encontrado=False
        while cola:
            _,g,u=heappop(cola)
            if not greedy and g!=costos[u]:continue
            if u==meta:encontrado=True;break
            expandidos+=1
            for nx,ny in self.vecinos(u%ancho,u//ancho):
                v=ny*ancho+nx;nuevo=padre[v]<0
                if greedy:
                    if not nuevo:continue
                elif not nuevo and g+1>=costos[v]:continue
                padre[v]=u
                if not greedy:costos[v]=g+1
                heappush(cola,(h(v) if greedy else g+1+h(v),g+1,v))
                descubiertos+=int(nuevo)
            operaciones+=1
            if operaciones%lote==0:
                tiempo+=perf_counter()-t0
                yield dict(descubiertos=descubiertos,expandidos=expandidos,tiempo=tiempo,estado='Buscando')
                t0=perf_counter()
        ruta=None
        if encontrado:
            ruta=[];u=meta
            while True:
                ruta.append((u%ancho,u//ancho))
                if u==origen:break
                u=int(padre[u])
                if len(ruta)%lote==0:
                    tiempo+=perf_counter()-t0
                    yield dict(descubiertos=descubiertos,expandidos=expandidos,tiempo=tiempo,estado='Reconstruyendo')
                    t0=perf_counter()
            ruta.reverse()
        tiempo+=perf_counter()-t0
        return dict(ruta=ruta,descubiertos=descubiertos,expandidos=expandidos,tiempo=tiempo,estado='Ruta encontrada' if encontrado else 'Sin camino')


    def _buscar_bidireccional(self, inicio, objetivo, lote):
        """Expande la frontera menor por niveles completos.

        Antes del primer encuentro las bolas visitadas son disjuntas. Al
        terminar el nivel se elige el encuentro de menor suma de distancias.
        No se termina prematuramente al encontrar cualquier arista de cruce.
        Descubiertos: posiciones unicas en la union de ambas busquedas.
        Expandidos: expansiones realizadas desde ambos extremos.
        """
        t0 = perf_counter()
        tiempo = 0.0
        descubiertos = expandidos = 0
        def datos(estado, ruta=None):
            return dict(ruta=ruta, descubiertos=descubiertos, expandidos=expandidos,
                        tiempo=tiempo, estado=estado,
                        criterio_nodos='Posiciones descubiertas unicas / expansiones de ambos extremos')
        if not self.valida(*inicio) or not self.valida(*objetivo):
            tiempo = perf_counter() - t0
            return datos('Puntos invalidos')
        if inicio == objetivo:
            descubiertos = 1
            tiempo = perf_counter() - t0
            return datos('Ruta encontrada', [inicio])
        alto, ancho = self.efectiva.shape
        total = alto * ancho
        origen = inicio[1]*ancho + inicio[0]
        meta = objetivo[1]*ancho + objetivo[0]
        padres = [np.full(total, -1, dtype=np.int32) for _ in range(2)]
        distancias = [np.full(total, -1, dtype=np.int32) for _ in range(2)]
        padres[0][origen] = origen; padres[1][meta] = meta
        distancias[0][origen] = 0; distancias[1][meta] = 0
        fronteras = [[origen], [meta]]
        descubiertos = 2
        encuentro = None
        mejor = total + 1
        libres = self.efectiva.reshape(-1)
        while fronteras[0] and fronteras[1] and encuentro is None:
            lado = 0 if len(fronteras[0]) <= len(fronteras[1]) else 1
            distancia = distancias[lado]
            otra = distancias[1-lado]
            padre = padres[lado]
            siguiente = []
            for u in fronteras[lado]:
                expandidos += 1
                for v in adyacentes(u, ancho, total):
                    if not libres[v]:
                        continue
                    if distancia[v] < 0:
                        distancia[v] = int(distancia[u]) + 1
                        padre[v] = u
                        siguiente.append(v)
                        if otra[v] < 0:
                            descubiertos += 1
                    if otra[v] >= 0:
                        costo = int(distancia[v]) + int(otra[v])
                        if costo < mejor:
                            mejor, encuentro = costo, v
                if expandidos % lote == 0:
                    tiempo += perf_counter() - t0
                    yield datos('Buscando')
                    t0 = perf_counter()
            fronteras[lado] = siguiente
        ruta = None
        if encuentro is not None:
            ruta = []
            u = encuentro
            while True:
                ruta.append((u % ancho, u // ancho))
                if u == origen:
                    break
                u = int(padres[0][u])
                if len(ruta) % lote == 0:
                    tiempo += perf_counter() - t0
                    yield datos('Reconstruyendo')
                    t0 = perf_counter()
            ruta.reverse()
            u = encuentro
            while u != meta:
                u = int(padres[1][u])
                ruta.append((u % ancho, u // ancho))
                if len(ruta) % lote == 0:
                    tiempo += perf_counter() - t0
                    yield datos('Reconstruyendo')
                    t0 = perf_counter()
        tiempo += perf_counter() - t0
        return datos('Ruta encontrada' if ruta is not None else 'Sin camino', ruta)
