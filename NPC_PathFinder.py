def leer_mapa(ruta):
    with open(ruta, "r") as archivo:

        lineas = archivo.readlines()

    # Buscar dónde empieza realmente el mapa
    inicio_mapa = lineas.index("map\n") + 1

    mapa = []

    for linea in lineas[inicio_mapa:]:
        mapa.append(list(linea.strip()))

    return mapa


mapa = leer_mapa("dataset/darkforest.map")


print("Filas:", len(mapa))
print("Columnas:", len(mapa[0]))

print(mapa[0][:20])

def contar_nodos(mapa):

    contador = 0

    for fila in mapa:
        for posicion in fila:

            if posicion == ".":
                contador += 1

    return contador


cantidad = contar_nodos(mapa)

print("Cantidad de nodos:", cantidad)

def mostrar_mapa(mapa, filas=30, columnas=50):

    for i in range(filas):
        print("".join(mapa[i][:columnas]))


mostrar_mapa(mapa, filas=40, columnas=80)

def mostrar_fragmento(mapa, inicio_fila, inicio_columna, filas, columnas):

    for i in range(inicio_fila, inicio_fila + filas):
        print("".join(mapa[i][inicio_columna:inicio_columna + columnas]))


mostrar_fragmento(mapa, 100, 100, 40, 80)