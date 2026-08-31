#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Revisión automática de la web publicada. La lanza GitHub todos los lunes.

Comprueba dos cosas que se pueden romper solas, sin que nadie toque nada:

1. Que todas las páginas del sitemap sigan respondiendo.
2. Que las categorías de superventas de Amazon sigan existiendo.

⚠️ EL PUNTO 2 ES EL IMPORTANTE. Amazon devuelve **HTTP 200 también para
categorías que no existen**: lo único que las delata es que el título de la
página dice "undefined". Si Amazon reorganiza sus categorías, los enlaces de la
portada se quedan muertos apuntando a una página vacía y nada avisa.

Si algo falla, este script termina con error, GitHub marca la ejecución en rojo
y manda un correo al dueño del repositorio. Esa es la alarma.
"""
import re
import sys
import urllib.error
import urllib.request

DOMINIO = "https://abuenprecio.github.io"

AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

problemas = []


def bajar(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "ignore")


def revisar_sitio():
    print("\n=== PÁGINAS DE LA WEB ===")
    try:
        _, xml = bajar("%s/sitemap.xml" % DOMINIO)
    except Exception as e:
        problemas.append("No se puede leer el sitemap: %s" % e)
        print("  ERROR leyendo el sitemap: %s" % e)
        return

    urls = re.findall(r"<loc>(.*?)</loc>", xml)
    print("  %d páginas en el sitemap" % len(urls))

    for url in urls:
        try:
            estado, _ = bajar(url, timeout=20)
            if estado != 200:
                problemas.append("%s responde %s" % (url, estado))
                print("  CAÍDA  %-58s %s" % (url.replace(DOMINIO, ""), estado))
        except Exception as e:
            problemas.append("%s no responde: %s" % (url, e))
            print("  CAÍDA  %-58s %s" % (url.replace(DOMINIO, ""), e))

    if not problemas:
        print("  Todas las páginas responden correctamente.")


def revisar_categorias_amazon():
    """Lee las categorías que la portada enlaza y comprueba que sigan vivas."""
    print("\n=== CATEGORÍAS DE SUPERVENTAS DE AMAZON ===")
    try:
        _, portada = bajar(DOMINIO)
    except Exception as e:
        problemas.append("No se puede leer la portada: %s" % e)
        return

    cats = sorted(set(re.findall(r"amazon\.[a-z.]+/gp/bestsellers/([\w-]+)/", portada)))
    if not cats:
        problemas.append("La portada no enlaza ninguna lista de superventas. "
                         "¿Se ha roto el generador?")
        print("  NINGUNA categoría enlazada en la portada.")
        return

    print("  %d categorías enlazadas desde la portada" % len(cats))
    bloqueos = 0

    for cat in cats:
        url = "https://www.amazon.es/gp/bestsellers/%s/" % cat
        try:
            _, html = bajar(url, timeout=30)
        except urllib.error.HTTPError as e:
            # Amazon bloquea a veces las IP de los servidores de GitHub. Eso no
            # significa que la categoría esté mal, así que no cuenta como fallo.
            bloqueos += 1
            print("  ?      %-28s Amazon bloqueó la petición (%s)" % (cat, e.code))
            continue
        except Exception as e:
            bloqueos += 1
            print("  ?      %-28s no comprobable (%s)" % (cat, e))
            continue

        m = re.search(r"<title>(.*?)</title>", html, re.S)
        titulo = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        nombre = re.search(r"populares en\s+(.+?)(?:\s*$|\s*\|)", titulo)
        nombre = nombre.group(1).strip() if nombre else ""

        if not nombre or nombre.lower().startswith("undefined"):
            problemas.append(
                "La categoría de Amazon '%s' ya no existe: responde 200 pero el título "
                "dice 'undefined'. El enlace de la portada está muerto. "
                "Quítala de datos/mercado.json." % cat)
            print("  MUERTA %-28s (200 pero 'undefined')" % cat)
        else:
            print("  OK     %-28s %s" % (cat, nombre))

    if bloqueos == len(cats):
        print("\n  Amazon ha bloqueado todas las peticiones desde este servidor.")
        print("  No es un fallo de la web: se comprobará en la siguiente ejecución.")


def main():
    print("Revisión semanal de %s" % DOMINIO)
    revisar_sitio()
    revisar_categorias_amazon()

    print("\n" + "=" * 66)
    if problemas:
        print("HAY %d PROBLEMA(S) QUE ARREGLAR:\n" % len(problemas))
        for p in problemas:
            print("  - " + p)
        print("=" * 66)
        return 1

    print("Todo correcto. Nada que hacer.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
