import re
import fitz
import pandas as pd
from pathlib import Path

def procesar_tarjeta(pdf_path: Path, output_base: Path):
    """
    Procesa un PDF de tarjeta, extrae operaciones y genera CSV + PDFs individuales.
    Devuelve un resumen como diccionario.
    """
    out_folder = output_base / "comprobantes_refinado"
    csv_path = out_folder / "operaciones.csv"
    out_pdf_folder = out_folder / "pdfs"
    out_folder.mkdir(exist_ok=True, parents=True)
    out_pdf_folder.mkdir(exist_ok=True)

    date_re = re.compile(r"\b\d{1,2}[./,]\d{1,2}[./,]\d{2,4}\b")
    amount_re = re.compile(r"^-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?-?$")

    def normalizar_importe(txt):
        sign = -1 if txt.strip().endswith("-") or txt.strip().startswith("-") else 1
        val = txt.replace(".", "").replace(",", ".").replace("-", "")
        try:
            return f"{sign * float(val):.2f}"
        except ValueError:
            return None

    def limpiar_nombre(texto):
        return re.sub(r"[^\w\-_\. ]", "_", texto).strip()[:80]

    def round_bbox(b, nd=1):
        x0, y0, x1, y1 = b
        return (round(float(x0), nd), round(float(y0), nd), round(float(x1), nd), round(float(y1), nd))

    def unique_path_with_counter(base_path):
        base = base_path.with_suffix("")
        ext = base_path.suffix
        i = 1
        candidate = base_path
        while candidate.exists():
            i += 1
            candidate = base.with_name(f"{base.name}_({i})").with_suffix(ext)
        return candidate

    print(f"📂 Abriendo PDF: {pdf_path.name}")
    doc = fitz.open(str(pdf_path))
    ops = []

    for p, page in enumerate(doc, start=1):
        words = page.get_text("words")
        if not words:
            continue
        df = pd.DataFrame(words, columns=["x0","y0","x1","y1","text","block","line","word"])
        df["ybin"] = (df["y0"]/2).round().astype(int)

        for ybin, grp in df.groupby("ybin"):
            grp = grp.sort_values("x0").reset_index(drop=True)
            textos = grp["text"].tolist()
            linea = " ".join(textos)
            if re.search(r"\d{2}[./]\d{2}[./]\d{4}\s*-\s*\d{2}[./]\d{2}[./]\d{4}", linea):
                continue
            if "TOTAL" in linea.upper():
                continue

            idx_fecha = next((i for i, t in enumerate(textos) if date_re.fullmatch(t)), None)
            if idx_fecha is None:
                continue
            idx_importe = next((len(textos)-1-i for i, t in enumerate(textos[::-1]) if amount_re.fullmatch(t)), None)
            if idx_importe is None:
                continue
            importe = normalizar_importe(textos[idx_importe])
            if importe is None:
                continue

            if idx_fecha < idx_importe:
                establecimiento = " ".join(textos[idx_fecha+1:idx_importe]).strip()
            else:
                establecimiento = " ".join(textos[idx_importe+1:idx_fecha]).strip()
            if not establecimiento:
                continue

            x0 = float(min(grp["x0"]))
            x1 = float(max(grp["x1"]))
            y0 = float(grp["y0"].min())
            y1 = float(grp["y1"].max())
            bbox = (x0, y0, x1, y1)

            ops.append({
                "page": p, "fecha": textos[idx_fecha],
                "establecimiento": establecimiento,
                "importe": importe, "bbox": bbox
            })

    # Deduplicar por bbox
    seen, ops_unicos = set(), []
    for o in ops:
        key = (o["page"], round_bbox(o["bbox"], nd=1))
        if key not in seen:
            seen.add(key)
            ops_unicos.append(o)

    df_ops = pd.DataFrame(ops_unicos)
    df_ops[["fecha", "establecimiento", "importe", "page"]].to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Crear PDFs resaltados
    for op in ops_unicos:
        doc_out = fitz.open(str(pdf_path))
        page_out = doc_out[op["page"] - 1]
        rect = fitz.Rect(*op["bbox"])
        annot = page_out.add_rect_annot(rect)
        annot.set_colors(stroke=(1,1,0), fill=(1,1,0))
        annot.set_opacity(0.35)
        annot.update()
        nombre = f"{limpiar_nombre(op['fecha'])}_{limpiar_nombre(op['establecimiento'])[:40]}_{op['importe'].replace('.', '_')}.pdf"
        ruta = unique_path_with_counter(out_pdf_folder / nombre)
        doc_out.save(str(ruta), deflate=True, clean=True, garbage=4)
        doc_out.close()

    doc.close()

    total_cargos = df_ops[df_ops["importe"].astype(float) > 0]["importe"].astype(float).sum()
    total_abonos = df_ops[df_ops["importe"].astype(float) < 0]["importe"].astype(float).sum()
    balance = total_cargos + total_abonos

    return {
        "operaciones": len(df_ops),
        "total_cargos": total_cargos,
        "total_abonos": total_abonos,
        "balance": balance,
        "csv": csv_path,
        "pdfs": out_pdf_folder
    }