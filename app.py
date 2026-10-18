# -*- coding: utf-8 -*-
"""
Prueba de recorte — Kbas Office  (TEST web)
Sube fotos de producto, elige el fondo (color) y si quieres sombra suave vertical,
y descarga el recorte SIN cambiar el encuadre ni las proporciones.
Para producción (50-70 TIFF) irá la versión de escritorio.
"""

import io, zipfile, os
from PIL import Image, ImageFilter
import streamlit as st

# ---------- Recorte (quitar fondo) ----------
@st.cache_resource(show_spinner=False)
def get_session(model_name):
    from rembg import new_session
    return new_session(model_name)

def quitar_fondo(pil_img, model_name, alpha_matting):
    from rembg import remove
    out = remove(
        pil_img.convert("RGB"),
        session=get_session(model_name),
        alpha_matting=alpha_matting,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=10,
    )
    return out.convert("RGBA")

# ---------- Montaje: MISMO marco + sombra de suelo ----------
def componer(cut_rgba, bg=(255, 255, 255), con_sombra=True, sombra_op=0.35, tipo="suelo"):
    cut = cut_rgba.convert("RGBA")
    W, H = cut.size                         # mismo tamaño/encuadre que la original
    canvas = Image.new("RGB", (W, H), bg)
    if con_sombra:
        a = cut.split()[-1]
        bbox = a.getbbox()                  # (izq, arriba, der, abajo) del objeto
        if bbox:
            l, t, r, b = bbox
            obj_w, obj_h = r - l, b - t
            black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
            vacio = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sil = Image.composite(black, vacio, a)         # silueta negra a marco completo
            shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))

            if tipo == "suelo":
                # sombra de suelo: silueta aplastada en vertical, anclada en la base,
                # leve desplazamiento a la izquierda (luz desde arriba-derecha)
                new_h = max(2, int(obj_h * 0.16))
                sil_crop = sil.crop(bbox).resize((obj_w, new_h))
                off_x = l - int(obj_w * 0.06)
                off_y = b - int(new_h * 0.55)
                shadow.paste(sil_crop, (off_x, off_y), sil_crop)
                blur = max(14, int(obj_w * 0.05))
            else:  # "proyectada": silueta entera lanzada abajo-izquierda
                shadow.paste(sil, (-int(obj_w * 0.06), int(obj_h * 0.05)), sil)
                blur = max(18, int(obj_w * 0.04))

            shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
            rr, gg, bb, al = shadow.split()
            al = al.point(lambda v: int(v * sombra_op))
            shadow = Image.merge("RGBA", (rr, gg, bb, al))
            canvas.paste(shadow, (0, 0), shadow)
    canvas.paste(cut, (0, 0), cut)
    return canvas

def to_jpg(img):
    buf = io.BytesIO(); img.convert("RGB").save(buf, "JPEG", quality=95); buf.seek(0); return buf

# ================= INTERFAZ =================
st.set_page_config(page_title="Prueba de recorte · Kbas", page_icon="✂️")
st.title("✂️ Prueba de recorte")
st.caption("Sube fotos, elige el fondo y la sombra, y descarga el recorte sin cambiar el encuadre. "
           "Es una prueba web para afinar el look; para el lote grande (50-70) irá la versión de escritorio. "
           "La primera foto tarda un poco (descarga el modelo la primera vez).")

PRESETS = {
    "Blanco (catálogo)": (255, 255, 255),
    "Gris 240 (El Corte Inglés)": (240, 240, 240),
    "Polène (web)": (249, 248, 246),
    "Color personalizado…": None,
}

c1, c2 = st.columns(2)
with c1:
    opcion = st.selectbox("Fondo", list(PRESETS.keys()))
    if opcion == "Color personalizado…":
        hexc = st.color_picker("Elige el color de fondo", "#F5F0EB")
        bg = tuple(int(hexc[i:i+2], 16) for i in (1, 3, 5))
    else:
        bg = PRESETS[opcion]
    st.markdown(f"<div style='height:26px;border:1px solid #ccc;border-radius:5px;"
                f"background:rgb{bg}'></div>", unsafe_allow_html=True)
    st.caption(f"RGB {bg[0]}, {bg[1]}, {bg[2]}")
with c2:
    sombra = st.checkbox("Sombra de suelo", value=True)
    tipo_sombra = st.radio("Tipo de sombra", ["suelo", "proyectada"],
                           help="'suelo' = charco suave bajo la base (apoyado en una superficie). "
                                "'proyectada' = silueta lanzada hacia abajo-izquierda.")
    sombra_op = st.slider("Intensidad de la sombra", 0.0, 0.6, 0.35, 0.05)

with st.expander("⚙ Opciones avanzadas del recorte"):
    modelo = st.selectbox("Modelo", ["u2net", "isnet-general-use", "birefnet-general"],
                          help="Si se come el asa o las cadenas, prueba 'birefnet-general' "
                               "(recorta mejor lo fino, pero es más pesado).")
    alpha = st.checkbox("Bordes finos (alpha matting) — en web mejor apagado, consume mucha memoria", value=False)

fotos = st.file_uploader("Fotos de producto (JPG o PNG)", type=["jpg", "jpeg", "png"],
                         accept_multiple_files=True)

if fotos:
    if st.button("Procesar", type="primary"):
        resultados = []
        barra = st.progress(0.0)
        for i, f in enumerate(fotos):
            img = Image.open(f)
            img.thumbnail((1200, 1200))     # preserva la proporción; tamaño reducido para no agotar la RAM del plan gratis
            try:
                cut = quitar_fondo(img, modelo, alpha)
            except Exception as e:
                st.error(f"Error con {f.name}: {e}")
                continue
            out = componer(cut, bg, sombra, sombra_op, tipo_sombra)
            resultados.append((os.path.splitext(f.name)[0] + ".jpg", out))
            barra.progress((i + 1) / len(fotos))
        barra.empty()

        if resultados:
            st.success(f"{len(resultados)} foto(s) procesada(s). Mira los bordes con lupa (sobre todo si el fondo no es blanco).")
            if len(resultados) > 1:
                zbuf = io.BytesIO()
                with zipfile.ZipFile(zbuf, "w") as z:
                    for nombre, img in resultados:
                        z.writestr(nombre, to_jpg(img).getvalue())
                zbuf.seek(0)
                st.download_button("⬇ Descargar todas (ZIP)", zbuf, "recortes.zip", "application/zip")
            for nombre, img in resultados:
                st.image(img, caption=nombre)
                st.download_button(f"⬇ {nombre}", to_jpg(img), nombre, "image/jpeg", key=nombre)
else:
    st.info("Sube una o varias fotos, elige el fondo y pulsa Procesar.")
