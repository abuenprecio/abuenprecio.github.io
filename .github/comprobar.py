#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Revisión automática de la web publicada. La lanza GitHub todos los lunes.

Comprueba lo que se puede romper **solo**, sin que nadie toque nada, y que
nadie notaría hasta que se lo encuentra un comprador:

1. Que todas las páginas del sitemap sigan respondiendo.
2. Que los vídeos de YouTube que la web enseña sigan existiendo.
3. Que la web no se haya quedado sin enlaces de producto.

Si algo falla, este script termina con error, GitHub marca la ejecución en rojo
y manda un correo al dueño del repositorio. Esa es la alarma.

⛔ TRES COSAS QUE ESTE COMPROBADOR **NO** HACE, Y NO ES UN OLVIDO
──────────────────────────────────────────────────────────────────────────────
· **No mira si un producto sigue vivo en Amazon.** Se intentó, y Amazon manda
  su página de bloqueo con código 200 y con texto parecido al de un producto
  retirado: de 45 productos daba 45 por muertos, y ninguno lo estaba. Un aviso
  que salta siempre es un aviso que se acaba ignorando. Y esquivar el bloqueo
  no se hace. Los enlaces muertos se cazan a mano, mirando la página.

· **No detecta si un vídeo se ha vuelto privado.** Solo si desaparece. Para
  distinguir público de privado haría falta la API de YouTube, o sea meter una
  credencial en un repositorio público. No compensa.

· **Antes comprobaba las categorías de superventas de Amazon** que enlazaba la
  portada. Esa sección se quitó de la web, y el comprobador se quedó buscando
  unos enlaces que ya no existen: **daba fallo todos los lunes avisando de un
  problema inventado**. Por eso ya no está.
──────────────────────────────────────────────────────────────────────────────
"""
import re
import sys
import urllib.error
import urllib.request

DOMINIO = "https://abuenprecio.github.io"

AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

problemas = []


def bajar(url, timeout=25, binario=False):
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        crudo = r.read()
        return r.status, crudo if binario else crudo.decode("utf-8", "ignore")


# --------------------------------------------------------------- 1. páginas
def revisar_paginas():
    print("\n=== PÁGINAS DE LA WEB ===")
    try:
        _, xml = bajar("%s/sitemap.xml" % DOMINIO)
    except Exception as e:
        problemas.append("No se puede leer el sitemap: %s" % e)
        print("  ERROR leyendo el sitemap: %s" % e)
        return []

    urls = re.findall(r"<loc>(.*?)</loc>", xml)
    print("  %d páginas en el sitemap" % len(urls))
    caidas, paginas = 0, []

    for url in urls:
        try:
            estado, html = bajar(url, timeout=20)
            if estado != 200:
                problemas.append("%s responde %s" % (url, estado))
                print("  CAÍDA  %-56s %s" % (url.replace(DOMINIO, ""), estado))
                caidas += 1
            else:
                paginas.append((url, html))
        except Exception as e:
            problemas.append("%s no responde: %s" % (url, e))
            print("  CAÍDA  %-56s %s" % (url.replace(DOMINIO, ""), e))
            caidas += 1

    if not caidas:
        print("  Todas responden correctamente.")
    return paginas


# ---------------------------------------------------------------- 2. vídeos
def revisar_videos(paginas):
    """¿Siguen existiendo los vídeos que la web enseña?

    Se mira la MINIATURA (`img.youtube.com/vi/<id>/hqdefault.jpg`), que es
    pública y no gasta cuota: si el vídeo ya no existe devuelve 404.

    ⚠️ Se probó primero con oEmbed y **no vale**: devuelve 401 para cualquier
    vídeo que tenga la inserción desactivada, aunque sea público. Los diez
    primeros nuestros dieron 401 estando públicos, y habría sido un aviso falso
    diez veces seguidas.
    """
    print("\n=== VÍDEOS DE YOUTUBE ===")
    ids = set()
    for _, html in paginas:
        ids.update(re.findall(r"youtube\.com/watch\?v=([\w-]{11})", html))
        ids.update(re.findall(r"youtu\.be/([\w-]{11})", html))
    if not ids:
        print("  La web no enlaza ningún vídeo todavía.")
        return

    print("  %d vídeos enlazados desde la web" % len(ids))
    for vid in sorted(ids):
        url = "https://img.youtube.com/vi/%s/hqdefault.jpg" % vid
        try:
            estado, datos = bajar(url, timeout=20, binario=True)
            # YouTube devuelve una imagen gris de 120x90 cuando el vídeo no
            # está: pesa muy poco. La de un vídeo real pasa de 10 KB.
            if estado == 200 and len(datos) > 5000:
                print("  OK     %s" % vid)
            else:
                problemas.append(
                    "El vídeo %s ya no está en YouTube, pero la web lo sigue "
                    "enseñando." % vid)
                print("  ROTO   %s (miniatura de %d bytes)" % (vid, len(datos)))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                problemas.append(
                    "El vídeo %s ya no está en YouTube, pero la web lo sigue "
                    "enseñando." % vid)
                print("  ROTO   %s (404)" % vid)
            else:
                print("  ?      %s no comprobable (%s)" % (vid, e.code))
        except Exception as e:
            print("  ?      %s no comprobable (%s)" % (vid, e))


# --------------------------------------------------- 3. enlaces de producto
def revisar_enlaces_producto(paginas):
    """Que la web no se haya quedado sin enlaces de afiliado.

    No se comprueba producto por producto contra Amazon (ver la cabecera). Lo
    que sí se comprueba es que el generador no haya dejado la web sin enlaces,
    que es un fallo silencioso y carísimo: la web seguiría pareciendo normal y
    no ganaría un céntimo.
    """
    print("\n=== ENLACES DE PRODUCTO ===")
    asins, con_tag = set(), 0
    for _, html in paginas:
        for m in re.finditer(r"amazon\.[a-z.]+/dp/([A-Z0-9]{10})[^\"'<> ]*", html):
            asins.add(m.group(1))
            if "tag=" in m.group(0):
                con_tag += 1

    if not asins:
        problemas.append(
            "La web no enlaza NINGÚN producto de Amazon. O se ha roto el "
            "generador, o se publicó una versión vacía.")
        print("  NINGÚN enlace de producto. Esto es grave.")
        return

    print("  %d productos distintos enlazados" % len(asins))
    if con_tag == 0:
        problemas.append(
            "Ningún enlace de Amazon lleva la etiqueta de afiliado (tag=). "
            "Las ventas no se estarían contando.")
        print("  NINGÚN enlace lleva tag de afiliado. Esto es grave.")
    else:
        print("  %d enlaces con etiqueta de afiliado" % con_tag)


def main():
    print("Revisión semanal de %s" % DOMINIO)
    paginas = revisar_paginas()
    if paginas:
        revisar_videos(paginas)
        revisar_enlaces_producto(paginas)

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
