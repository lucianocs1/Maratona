"""PDF dos relatórios (mensal, comprovante do aviso, auditoria), no visual do Norte (fpdf2, fontes Latin-1).

Recebe o título, quem gerou, o código de verificação (que aponta para a linha da auditoria que
registrou o relatório) e as seções: parágrafos, números (rótulo e valor) e tabelas. Todo texto passa
pelo _l1 (Latin-1), como no roteiro da rádio.
"""

from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from . import traducao
from .pdf_radio import AMBAR, CINZA, MARCA, MARE, NOITE, _l1


class _Relatorio(FPDF):
    rodape = ""
    idioma = "pt-BR"

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*CINZA)
        self.cell(0, 6, _l1(self.rodape + traducao.pdf(self.idioma, "pagina", n=self.page_no())), align="C")


def documento(titulo: str, subtitulo: str, gerado_por: str, codigo: str, secoes: list[tuple], aviso_ficticio: str,
              gerado_em: datetime, paisagem: bool = False, idioma: str = "pt-BR") -> bytes:
    """secoes: ("titulo", texto) | ("texto", texto) | ("numeros", [(rotulo, valor), ...]) | ("tabela", cabecalho, linhas[, larguras]).
    idioma: os textos fixos do PDF (Fase K); quem chama traduz os rótulos das seções."""
    T = lambda chave, **v: traducao.pdf(idioma, chave, **v)
    pdf = _Relatorio(orientation="L" if paisagem else "P", format="A4", unit="mm")
    pdf.idioma = idioma
    largura = 297 if paisagem else 210
    pdf.rodape = T("rodape_doc", titulo=titulo, codigo=codigo)
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(True, 18)
    pdf.set_title(_l1(titulo))
    pdf.set_lang(idioma)
    pdf.set_author("Norte")
    pdf.add_page()
    pdf.set_fill_color(*NOITE)
    pdf.rect(0, 0, largura, 24, "F")
    pdf.set_fill_color(255, 255, 255)   # o fundo das tabelas (o fpdf2 usa a cor de preenchimento atual)
    try:
        pdf.image(str(MARCA), x=12, y=3.5, h=17)
    except Exception:  # noqa: BLE001
        pass
    pdf.set_xy(33, 5)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, "Norte")
    pdf.set_xy(33, 13)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*AMBAR)
    pdf.cell(0, 6, _l1(T("slogan")))
    pdf.set_y(29)
    pdf.set_text_color(*NOITE)
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 8, _l1(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 5, _l1(subtitulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*MARE)
    pdf.multi_cell(0, 5, _l1(T("gerado_simples", quem=gerado_por, d=gerado_em, codigo=codigo)),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    cabeca = FontFace(emphasis="BOLD", fill_color=(245, 248, 251))
    for s in secoes:
        tipo = s[0]
        if tipo == "titulo":
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11.5)
            pdf.set_text_color(*MARE)
            pdf.multi_cell(0, 6.5, _l1(s[1]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*NOITE)
        elif tipo == "texto":
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(0, 5, _l1(s[1]), new_x="LMARGIN", new_y="NEXT")
        elif tipo == "numeros":
            pdf.set_font("Helvetica", "", 9.5)
            with pdf.table(col_widths=(2, 1), text_align=("LEFT", "RIGHT"), first_row_as_headings=False,
                           line_height=5.5, borders_layout="HORIZONTAL_LINES") as t:
                for rotulo, valor in s[1]:
                    linha = t.row()
                    linha.cell(_l1(rotulo))
                    linha.cell(_l1(valor))
        elif tipo == "tabela":
            cab, linhas = s[1], s[2]
            if not linhas:
                pdf.set_font("Helvetica", "I", 9)
                pdf.multi_cell(0, 5, _l1(T("nada")), new_x="LMARGIN", new_y="NEXT")
                continue
            pdf.set_font("Helvetica", "", 8)
            larguras = s[3] if len(s) > 3 else None
            with pdf.table(headings_style=cabeca, line_height=4.6, borders_layout="SINGLE_TOP_LINE", repeat_headings=1,
                           col_widths=larguras) as t:
                h = t.row()
                for c in cab:
                    h.cell(_l1(c))
                for ln in linhas:
                    r = t.row()
                    for v in ln:
                        r.cell(_l1("" if v is None else v))
        pdf.ln(1.5)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 4.2, _l1(T("nota") + T("nota_doc") + traducao.aviso_ficticio(idioma, aviso_ficticio)),
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ---------- Fase H: o documento completo (todos os relatórios menos o comprovante) ----------
class _Completo(FPDF):
    rodape = ""
    idioma = "pt-BR"

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*CINZA)
        self.cell(0, 6, _l1(self.rodape + traducao.pdf(self.idioma, "pagina_de", n=self.page_no())) + "{nb}", align="C")


def _grafico(pdf: FPDF, s: dict, largura: float, idioma: str = "pt-BR") -> None:
    """Barras (âmbar) com os valores; a projeção (quando há) em barras tracejadas sem preenchimento."""
    valores = list(s["valores"])
    proj = s.get("projecao") or [None] * len(valores)
    todos = [v for v in valores + proj if v]
    if not todos:
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(0, 5, _l1(traducao.pdf(idioma, "nada")), new_x="LMARGIN", new_y="NEXT")
        return
    maximo, altura, n = max(todos), 38, len(valores)
    x0, y0 = pdf.l_margin, pdf.get_y() + 4
    if y0 + altura + 14 > pdf.h - pdf.b_margin:
        pdf.add_page()
        x0, y0 = pdf.l_margin, pdf.get_y() + 4
    passo = largura / n
    fmt = (lambda v: f"{v:,.0f}".replace(",", ".")) if s.get("formato") == "dinheiro" else (lambda v: f"{v:g}")
    pdf.set_draw_color(220, 227, 223)
    pdf.line(x0, y0 + altura, x0 + largura, y0 + altura)
    pdf.set_font("Helvetica", "", 6.5)
    for i in range(n):
        x = x0 + i * passo + passo * 0.18
        w = passo * 0.64
        for v, e_projecao in ((valores[i], False), (proj[i], True)):
            if not v:
                continue
            h = altura * v / maximo
            if e_projecao:
                pdf.set_draw_color(*AMBAR)
                pdf.set_dash_pattern(dash=1, gap=1)
                pdf.rect(x, y0 + altura - h, w, h)
                pdf.set_dash_pattern()
            else:
                pdf.set_fill_color(*AMBAR)
                pdf.rect(x, y0 + altura - h, w, h, "F")
            pdf.set_text_color(*NOITE)
            pdf.set_xy(x - 2, y0 + altura - h - 3.5)
            pdf.cell(w + 4, 3, _l1(fmt(v)), align="C")
        pdf.set_text_color(*CINZA)
        pdf.set_xy(x0 + i * passo, y0 + altura + 1)
        pdf.cell(passo, 3, _l1(str(s["rotulos"][i])[:14]), align="C")
    pdf.set_fill_color(255, 255, 255)
    pdf.set_draw_color(220, 227, 223)
    pdf.set_y(y0 + altura + 6)
    if any(proj):
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.cell(0, 4, _l1(traducao.pdf(idioma, "barras")), new_x="LMARGIN", new_y="NEXT")


def documento_completo(doc: dict, subtitulo: str, gerado_por: str, codigo: str, gerado_em: datetime, aviso_ficticio: str,
                       paisagem: bool = True, idioma: str = "pt-BR") -> bytes:
    """O documento completo; idioma: o de quem gera (Fase K). O documento já chega traduzido (traducao.documento)."""
    T = lambda chave, **v: traducao.pdf(idioma, chave, **v)
    pdf = _Completo(orientation="L" if paisagem else "P", format="A4", unit="mm")
    pdf.idioma = idioma
    largura_pagina = 297 if paisagem else 210
    pdf.rodape = T("gerado", quem=gerado_por, d=gerado_em, codigo=codigo)
    pdf.alias_nb_pages()
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(True, 18)
    pdf.set_title(_l1(doc["titulo"]))
    pdf.set_lang(idioma)
    pdf.set_author("Norte")
    pdf.set_creation_date(gerado_em)
    pdf.add_page()
    pdf.set_fill_color(*NOITE)
    pdf.rect(0, 0, largura_pagina, 24, "F")
    pdf.set_fill_color(255, 255, 255)
    try:
        pdf.image(str(MARCA), x=12, y=3.5, h=17)
    except Exception:  # noqa: BLE001
        pass
    pdf.set_xy(33, 5)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, "Norte")
    pdf.set_xy(33, 13)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*AMBAR)
    pdf.cell(0, 6, _l1(T("slogan")))
    pdf.set_y(29)
    pdf.set_text_color(*NOITE)
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 8, _l1(doc["titulo"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 5, _l1(subtitulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*MARE)
    pdf.multi_cell(0, 5, _l1(pdf.rodape), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    for a in doc.get("alertas") or []:
        pdf.set_fill_color(253, 236, 234)
        pdf.set_text_color(180, 35, 24)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.multi_cell(0, 6, _l1(T("alerta", a=a)), fill=True, padding=1.5, new_x="LMARGIN", new_y="NEXT")
        pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(*NOITE)
    pdf.set_font("Helvetica", "B", 11.5)
    pdf.set_text_color(*MARE)
    pdf.cell(0, 7, _l1(T("resumo")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*NOITE)
    pdf.set_font("Helvetica", "", 9.5)
    with pdf.table(col_widths=(3, 2, 2.4), text_align=("LEFT", "RIGHT", "RIGHT"), first_row_as_headings=False, line_height=5.4,
                   borders_layout="HORIZONTAL_LINES") as t:
        for item in doc["resumo"]:
            r = t.row()
            r.cell(_l1(item["rotulo"]))
            r.cell(_l1(item["valor"]))
            r.cell(_l1(" · ".join(f"{c['texto']} vs {c['contra']}" for c in item.get("comparacoes") or [])))
    cabeca = FontFace(emphasis="BOLD", fill_color=(245, 248, 251))
    for s in doc["secoes"]:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*MARE)
        pdf.multi_cell(0, 6.5, _l1(s["titulo"]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*NOITE)
        if s["tipo"] == "texto":
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(0, 5, _l1(s["texto"]), new_x="LMARGIN", new_y="NEXT")
        elif s["tipo"] == "lista":
            pdf.set_font("Helvetica", "", 9)
            for it in s["itens"] or ["—"]:
                pdf.multi_cell(0, 4.8, _l1(f"- {it}"), new_x="LMARGIN", new_y="NEXT")
        elif s["tipo"] == "grafico":
            _grafico(pdf, s, largura_pagina - 28, idioma)
        elif s["tipo"] == "tabela":
            if not s["linhas"]:
                pdf.set_font("Helvetica", "I", 9)
                pdf.multi_cell(0, 5, _l1(T("nada")), new_x="LMARGIN", new_y="NEXT")
                continue
            pdf.set_font("Helvetica", "", 7.5 if len(s["colunas"]) > 8 else 8.2)
            with pdf.table(headings_style=cabeca, line_height=4.4, borders_layout="SINGLE_TOP_LINE", repeat_headings=1) as t:
                h = t.row()
                for c in s["colunas"]:
                    h.cell(_l1(c))
                for ln in s["linhas"]:
                    r = t.row()
                    for v in ln:
                        r.cell(_l1("" if v is None else v))
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*MARE)
    pdf.cell(0, 8, _l1(T("como")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*NOITE)
    pdf.set_font("Helvetica", "", 9.5)
    for t_ in doc["como_calculamos"]:
        pdf.multi_cell(0, 5, _l1(f"- {t_}"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 4.2, _l1(T("nota") + T("nota_completo") + traducao.aviso_ficticio(idioma, aviso_ficticio)),
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
